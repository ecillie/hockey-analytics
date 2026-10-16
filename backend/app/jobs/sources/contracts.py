"""Strict Cap Space contracts with an explicitly mapped CapWages fallback."""
import re

from app.jobs.shared.execution import JobOperation
from app.jobs.shared.identity import UnresolvedIdentity
from app.jobs.shared.normalization import iso_date, money_cents
from app.jobs.shared.source_requests import SourceRequestError
from .common import batches, positive_id, scan, season_ready, source_record, stable_id
from .html import Document


def money(value):
    if value is None or value in ("", "-", "—", "–", "N/A"):
        return None
    if isinstance(value, str):
        value = value.replace("$", "").replace(",", "").strip()
    return money_cents(value)


def season(value):
    match = re.fullmatch(r"(\d{4})\s*[-–]\s*(\d{2}|\d{4})", str(value))
    if not match or int(match[2]) != (int(match[1]) + 1) % (100 if len(match[2]) == 2 else 10000):
        raise ValueError("Malformed contract season")
    return int(match[1])


def terms(row):
    fields = {re.sub(r"[^a-z]", "", key.lower()): value for key, value in row.items()}
    cap_hit = money(fields.get("caphit"))
    if cap_hit is None:
        raise ValueError("Contract season has no cap hit")
    salary = fields.get("nhlsalary", fields.get("basesalary"))
    slide = isinstance(salary, str) and "slide" in salary.lower()
    return {"season": season(fields["season"]), "cap_hit": cap_hit, "is_slide": slide,
            "base_salary": None if slide else money(salary),
            "signing_bonus": money(fields.get("signingbonus")),
            "performance_bonus": money(fields.get("perfbonuses", fields.get("performancebonus"))),
            "clause": fields.get("clause") or None}


def parse_capspace(body, nhl_id):
    document = Document(body)
    # An embedded identity, when supplied, must match the requested durable ID.
    scripts = [node for node in document.root.descendants("script") if node.attrs.get("id") == "__NEXT_DATA__"]
    if scripts:
        page = document.next_data()["props"]["pageProps"]
        person = page.get("player", page.get("person", {}))
        if person.get("nhlId") is not None and positive_id(person["nhlId"]) != nhl_id:
            raise UnresolvedIdentity("Cap Space returned a different NHL player")
    blocks = [node for node in document.root.descendants()
              if "contract" in (node.attrs.get("class") or "").split()]
    result = []
    for block in blocks:
        text = block.text()
        rows = []
        for table in block.descendants("table"):
            header = None
            for tr in table.descendants("tr"):
                cells = [node for node in tr.children if not isinstance(node, str) and node.tag in ("td", "th")]
                values = [cell.text() for cell in cells]
                keys = [re.sub(r"[^a-z]", "", value.lower()) for value in values]
                if "season" in keys and "caphit" in keys:
                    if header is not None:
                        raise ValueError("Repeated contract season header")
                    header = keys
                    continue
                if header is None or not values:
                    continue
                if values[0].lower().startswith(("buyout", "termination", "cap recapture")):
                    break  # Auxiliary charges are not agreement salary terms.
                if len(values) != len(header):
                    raise ValueError("Changed/incomplete contract table row")
                rows.append(terms(dict(zip(header, values))))
        if not rows:
            raise ValueError("Contract block has no valid covered seasons")
        rows.sort(key=lambda row: row["season"])
        years = [row["season"] for row in rows]
        if years != list(range(years[0], years[-1] + 1)):
            raise ValueError("Duplicate or missing contract seasons")
        signed = re.search(r"Signing Date\s*:\s*(\d{4}-\d{2}-\d{2})", text)
        explicit_id = block.attrs.get("data-contract-id") or block.attrs.get("data-external-id")
        if signed is None and not explicit_id:
            raise ValueError("Contract lacks a stable agreement identity")
        signed_on = iso_date(signed[1]) if signed else None
        headings = [node.text() for node in block.descendants() if node.tag in ("h2", "h3", "strong")]
        contract_type = next((heading for heading in headings if "contract" in heading.lower()), None)
        published_term = re.search(r"Seasons?\s*:\s*(\d+)", text)
        if published_term and int(published_term[1]) != len(rows) and not any(row["is_slide"] for row in rows):
            raise ValueError("Published contract term disagrees with covered seasons")
        total = re.search(r"Total Value\s*:\s*(\$?[\d,]+(?:\.\d+)?)", text)
        expiry = re.search(r"Expiration Status\s*:\s*(RFA|UFA)", text)
        signing_teams = [node.attrs["href"].split("/team/")[1].split("/")[0]
                         for node in block.descendants("a") if (node.attrs.get("href") or "").startswith("/team/")]
        signing_team = re.search(r"Signing Team\s*:\s*(.*?)(?=\s*\|?\s*Season\b|\s*Cap Hit\b|$)", text)
        result.append({"source_id": explicit_id or f"{nhl_id}/{signed_on}/{years[0]}",
            "start_season": years[0], "end_season": years[-1], "term_years": len(rows),
            "signed_on": signed_on, "contract_type": contract_type,
            "is_entry_level": bool(contract_type and ("entry" in contract_type.lower() or "elc" in contract_type.lower())),
            "total_value": money(total[1]) if total else None, "expiry_status": expiry[1] if expiry else None,
            "team_abbrev": signing_teams[0] if signing_teams else None,
            "team_name": signing_team[1].strip(" |") if signing_team else None,
            "published_term": int(published_term[1]) if published_term else None, "terms": rows})
    if not blocks and "No recorded contracts" not in document.root.text():
        raise ValueError("Unrecognized Cap Space contract page")
    return result


def parse_capwages(body, nhl_id):
    page = Document(body).next_data()["props"]["pageProps"]
    person = page.get("player", page.get("person"))
    if not isinstance(person, dict) or positive_id(person.get("nhlId")) != nhl_id:
        raise UnresolvedIdentity("CapWages fallback lacks a matching NHL identity")
    contracts = person.get("contracts", page.get("contracts"))
    if not isinstance(contracts, list):
        raise ValueError("CapWages lacks explicit contract enumeration")
    result = []
    for raw in contracts:
        rows = [terms(row) for row in raw.get("details", raw.get("seasons", []))]
        if not rows or not raw.get("id", raw.get("contractId")):
            raise ValueError("CapWages agreement lacks stable identity or terms")
        rows.sort(key=lambda row: row["season"])
        years = [row["season"] for row in rows]
        if years != list(range(years[0], years[-1] + 1)):
            raise ValueError("CapWages terms are incomplete/duplicated")
        declared_term = raw.get("term", raw.get("termYears", raw.get("seasonsCount")))
        if declared_term is not None and positive_id(declared_term) != len(rows) and not any(row["is_slide"] for row in rows):
            raise ValueError("CapWages published term disagrees with covered seasons")
        contract_type = raw.get("type", raw.get("contractType"))
        result.append({"source_id": str(raw.get("id", raw.get("contractId"))),
            "start_season": years[0], "end_season": years[-1], "term_years": len(rows),
            "signed_on": iso_date(raw.get("signingDate")), "contract_type": contract_type,
            "is_entry_level": bool(contract_type and "entry" in contract_type.lower()),
            "total_value": money(raw.get("value", raw.get("totalValue"))),
            "expiry_status": raw.get("expiryStatus"), "team_abbrev": raw.get("signingTeamAbbrev"),
            "team_name": raw.get("signingTeam"), "terms": rows})
    return result


def collect(ctx, cursor, *, fallback=True):
    if ctx.client is None:
        raise ValueError("Contract collection requires a configured SourceClient")
    items, references, candidates = [], {}, {}
    pending = []
    if ctx.config.first_season <= ctx.config.current_season <= ctx.config.last_season:
        pending = [row for row in scan(ctx, "refresh_requests")
                   if ctx.lookup("refresh_completions", (row.request_id,)) is None]
        for row in pending:
            candidates.setdefault(row.player_id, set()).add(ctx.config.current_season)
    # Audit salary coverage against actual NHL participation, including retirees.
    for row in scan(ctx, "basic_stats"):
        if ctx.config.first_season <= row.season <= ctx.config.last_season and row.games_played > 0:
            candidates.setdefault(row.player_id, set()).add(row.season)
    for row in scan(ctx, "memberships"):
        if ctx.config.first_season <= row.season <= ctx.config.last_season:
            candidates.setdefault(row.player_id, set()).add(row.season)
    if not candidates:
        raise ValueError("Contract coverage requires accepted player participation/membership evidence")
    for player_id, requested in sorted(candidates.items()):
        player = ctx.lookup("player_profiles", (player_id,))
        if player is None or player.nhl_player_id is None:
            raise UnresolvedIdentity(f"Missing NHL identity for contract player {player_id}")
        nhl_id, source, failure = player.nhl_player_id, "capspace", None
        # Require the accepted NHL-ID addressing mapping before following a page.
        if ctx.resolve("capspace", "player", str(nhl_id)) != player_id:
            raise UnresolvedIdentity("Contract mapping disagrees with NHL identity")
        try:
            body = ctx.client.get(source, f"https://cap-space.com/person/nhl:{nhl_id}").decode("utf-8")
            agreements = parse_capspace(body, nhl_id)
        except UnresolvedIdentity:
            raise
        except (SourceRequestError, ValueError, UnicodeError) as exc:
            failure, agreements = exc, []
        covered = {row["season"] for agreement in agreements for row in agreement["terms"]}
        if not requested <= covered:
            choices = [mapping for mapping in scan(ctx, "source_mappings", source="capwages", entity_type="player")
                       if mapping.canonical_id == player_id]
            if fallback and len(choices) == 1:
                # Partial primary coverage is a gap, not permission to silently merge competing agreements.
                if requested & covered:
                    raise ValueError(f"Partial Cap Space coverage for {player_id}; review before merging fallback")
                source = "capwages"
                slug = choices[0].source_id
                if not re.fullmatch(r"[a-z0-9-]+", slug):
                    raise ValueError("Invalid mapped CapWages profile slug")
                body = ctx.client.get(source, f"https://capwages.com/players/{slug}").decode("utf-8")
                agreements = parse_capwages(body, nhl_id)
                covered = {row["season"] for agreement in agreements for row in agreement["terms"]}
            if not requested <= covered:
                raise ValueError(f"Unavailable required contract seasons for player {player_id}: {sorted(requested-covered)}; {failure or 'source gap'}")
        for agreement in agreements:
            if not any(year in requested for year in range(agreement["start_season"], agreement["end_season"] + 1)):
                continue
            agreement_id = stable_id(source, "contract", nhl_id, agreement["source_id"])
            for existing in scan(ctx, "contracts", player_id=player_id):
                if (existing.contract_id != agreement_id and existing.start_season <= agreement["end_season"]
                        and agreement["start_season"] <= existing.end_season):
                    raise UnresolvedIdentity("Overlapping agreements/source conflict require explicit review")
            for year in range(max(2008, agreement["start_season"]), agreement["end_season"] + 1):
                existing = ctx.lookup("seasons", (year,))
                references[year] = source_record(ctx, "seasons",
                    existing or {"season": year, "end_year": year+1, "label": f"{year}-{str(year+1)[2:]}"},
                    source=source, key=f"contract-season/{year}", raw=body)
            payload = {key: agreement[key] for key in ("start_season", "end_season", "term_years", "signed_on", "contract_type", "is_entry_level", "total_value", "expiry_status")}
            payload.update(contract_id=agreement_id, player_id=player_id,
                clauses={"season_clauses": {str(row["season"]): row["clause"] for row in agreement["terms"] if row["clause"]},
                         "published_term_years": agreement.get("published_term")})
            items.append(source_record(ctx, "contracts", {"record": payload, "team_abbrev": agreement["team_abbrev"],
                "team_name": agreement["team_name"]}, source=source, key=f"{nhl_id}/{agreement['source_id']}", raw=body))
            for term in agreement["terms"]:
                if term["season"] < ctx.config.first_season or (term["season"] > ctx.config.last_season and term["season"] <= ctx.config.current_season):
                    continue
                payload = {key: value for key, value in term.items() if key != "clause"}
                payload.update(contract_id=agreement_id, player_id=player_id)
                items.append(source_record(ctx, "contract_seasons", payload, source=source,
                    key=f"{nhl_id}/{agreement['source_id']}/{term['season']}", raw=body))
    # Coalesce requests by player above; acknowledge each exact cause only after
    # the complete collection has validated. Failed/resumed work retains pending
    # requests until its acknowledgement batch commits.
    completions = [source_record(ctx, "refresh_completions", {
        "request_id": row.request_id, "run_id": ctx.run.run_id,
        "completed_at": ctx.run.started_at}, source="contract-refresh",
        key=row.request_id, raw=row.model_dump(mode="json")) for row in pending]
    yield from batches(ctx, (*[references[year] for year in sorted(references)], *items, *completions), cursor, partition="contracts")


def normalize(item, ctx):
    if item.dataset != "contracts":
        return item.payload
    payload = dict(item.payload["record"])
    abbreviation, name = item.payload["team_abbrev"], item.payload["team_name"]
    if abbreviation:
        choices = scan(ctx, "team_seasons", season=max(2008, payload["start_season"]), abbreviation=abbreviation)
        if len(choices) != 1:
            raise UnresolvedIdentity("Contract signing team needs a dated abbreviation mapping")
        payload["signing_team_id"] = choices[0].team_id
    elif name:
        payload["signing_team_id"] = ctx.resolve(item.observation.source, "team", f"name:{name}")
    return payload


def operation(*, fallback=True):
    return JobOperation(lambda ctx, cursor: collect(ctx, cursor, fallback=fallback), normalize, ready=season_ready)
