"""HTML source boundary for saved contract profiles."""

import json

from app.ScriptingFiles.FullDataScript.contracts.errors import (
    ContractDocumentError,
    DocumentFailure,
)
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel, Field, InstanceOf, ValidationError


class ContractPage(BaseModel):
    player: dict[str, object] | None = None
    person: dict[str, object] | None = None
    contracts: list[dict[str, object]] | None = None
    playersArray: list[list[object]] | None = None


class PageProps(BaseModel):
    pageProps: ContractPage = Field(default_factory=ContractPage)


class PagePayload(BaseModel):
    props: PageProps = Field(default_factory=PageProps)


def validate_page(payload: dict[str, object]) -> ContractPage:
    try:
        return PagePayload.model_validate(payload).props.pageProps
    except ValidationError as error:
        raise ContractDocumentError(
            reason=DocumentFailure.INVALID_PAYLOAD, source="embedded JSON"
        ) from error


class SourceDocument(BaseModel):
    html: str
    root: InstanceOf[BeautifulSoup]

    @property
    def next_data(self) -> tuple[dict[str, object], ...]:
        return tuple(
            payload
            for node in self.root.find_all("script", id="__NEXT_DATA__")
            if (payload := decode_page_payload(node)) is not None
        )


def decode_page_payload(node: Tag) -> dict[str, object] | None:
    try:
        payload = json.loads(node.get_text())
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def tag_text(node: Tag) -> str:
    return " ".join(node.get_text(" ", strip=True).split())


def tag_attribute(node: Tag, name: str) -> str | None:
    value = node.get(name)
    if isinstance(value, str):
        return value
    return None


def parse_source_document(html: str) -> SourceDocument:
    return SourceDocument(html=html, root=BeautifulSoup(html, "html.parser"))
