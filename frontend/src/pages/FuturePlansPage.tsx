import { useRef, type KeyboardEvent } from 'react'
import { useSearchParams } from 'react-router-dom'

type PlanSection = {
  eyebrow: string
  title: string
  description: string
  items: string[]
}

type PlanTab = {
  id: string
  label: string
  kicker: string
  title: string
  description: string
  sections: PlanSection[]
}

const tabs: PlanTab[] = [
  {
    id: 'data-automation',
    label: 'Data & Automation',
    kicker: 'Foundation',
    title: 'A reliable data engine',
    description: 'Keep every view current, traceable, and ready for the models that build on top of it.',
    sections: [
      {
        eyebrow: '01 · Current priority',
        title: 'Automated data updates',
        description: 'Replace manual refreshes with scheduled, observable pipelines throughout the NHL season.',
        items: [
          'Refresh player, team, contract, roster, schedule, game, and salary-cap data',
          'Validate new records before publishing and flag missing, duplicate, or unexpected data',
          'Monitor failures, alert on incomplete runs, and safely rerun failed updates',
          'Show dataset freshness and preserve historical contract, roster, and performance snapshots',
        ],
      },
      {
        eyebrow: '02 · Expanded coverage',
        title: 'Broader hockey data',
        description: 'Connect a player\'s path across professional and developmental hockey.',
        items: [
          'Add AHL, NCAA men\'s hockey, Canadian major junior, and other reliable leagues',
          'Resolve player identities across leagues, teams, and seasons',
          'Build prospect profiles, development timelines, and complete career histories',
          'Create league-adjusted metrics and NHL-equivalency models',
        ],
      },
      {
        eyebrow: '03 · Trust layer',
        title: 'Model transparency & data quality',
        description: 'Make every dataset, metric, and model understandable and testable.',
        items: [
          'Publish methodology, metric definitions, data sources, and known limitations',
          'Display model versions, training dates, confidence ranges, and freshness indicators',
          'Separate recorded statistics, calculated metrics, and predictions clearly',
          'Report historical backtests and add automated checks across pipelines, APIs, and models',
        ],
      },
    ],
  },
  {
    id: 'player-analytics',
    label: 'Player Analytics',
    kicker: 'Performance',
    title: 'Understand how players create value',
    description: 'Move from season totals to contextual performance, development paths, and explainable forecasts.',
    sections: [
      {
        eyebrow: '01 · Deeper context',
        title: 'Deeper player analytics',
        description: 'Expand player pages into a complete view of performance, role, and environment.',
        items: [
          'Add play-by-play and game-by-game performance with rolling trends',
          'Build interactive shot maps, expected-goals views, and scoring-chance analysis',
          'Separate even-strength, power-play, and penalty-kill performance',
          'Account for teammates, opponents, usage, line combinations, and defensive pairings',
          'Create player similarity, age-curve, and career-development views',
        ],
      },
      {
        eyebrow: '02 · Forward view',
        title: 'Growth & regression models',
        description: 'Estimate where performance is going—not only where it has been.',
        items: [
          'Publish next-season and multi-season performance projections',
          'Estimate peak age, breakout probability, decline risk, role, and ice-time changes',
          'Use age, position, league history, recent results, and comparable career paths',
          'Show confidence ranges, important model factors, and accuracy over time',
          'Maintain distinct models for forwards, defensemen, and goaltenders',
        ],
      },
    ],
  },
  {
    id: 'contracts-salary',
    label: 'Contracts & Salary',
    kicker: 'Market value',
    title: 'Connect projected impact to contract value',
    description: 'Separate on-ice value from market forces, then make the risk and opportunity legible.',
    sections: [
      {
        eyebrow: '01 · Valuation',
        title: 'Salary & contract models',
        description: 'Estimate what future performance should be worth in the NHL salary-cap environment.',
        items: [
          'Predict expected salary, cap hit, fair value, and recommended contract term',
          'Model unrestricted and restricted free agents separately',
          'Estimate surplus value and negative value over the life of a contract',
          'Adjust historical comparisons for changes in the salary cap',
        ],
      },
      {
        eyebrow: '02 · Risk',
        title: 'Contract-risk analysis',
        description: 'Make the downside of term, age, health, and regression visible before it arrives.',
        items: [
          'Estimate performance and value ranges across every remaining contract season',
          'Measure risk from age, term, injuries, role changes, and projected regression',
          'Surface team-level contract efficiency and long-term commitments',
        ],
      },
      {
        eyebrow: '03 · Market context',
        title: 'Comparable-contract analysis',
        description: 'Show how similar players were valued under comparable market conditions.',
        items: [
          'Match players by role, position, production, age, and signing status',
          'Compare term, cap percentage, signing date, and projected value',
          'Provide clear comps for negotiations, free agency, and roster planning',
        ],
      },
    ],
  },
  {
    id: 'teams-games',
    label: 'Teams & Games',
    kicker: 'Team context',
    title: 'See how rosters become results',
    description: 'Bring performance, lineup decisions, schedule context, and cap flexibility into one view.',
    sections: [
      {
        eyebrow: '01 · Roster construction',
        title: 'Team analytics & salary-cap tools',
        description: 'Build complete team views for performance, depth, commitments, and flexibility.',
        items: [
          'Add team advanced statistics, shot maps, scoring profiles, and special-teams analysis',
          'Map roster strengths, weaknesses, lineups, and depth by position',
          'Show contract ledgers, multi-year commitments, LTIR, buried contracts, and accrued space',
          'Create cap scenarios, roster tools, team projections, and playoff probabilities',
        ],
      },
      {
        eyebrow: '02 · Matchups',
        title: 'Game-by-game analysis & predictions',
        description: 'Explain expected outcomes before the game and the drivers of the result afterward.',
        items: [
          'Publish game previews, matchup comparisons, win probability, and expected scoring',
          'Include projected goaltending, recent form, rest, travel, and schedule effects',
          'Add in-game probability when reliable live data is available',
          'Track prediction accuracy and show what drove each final result',
        ],
      },
    ],
  },
  {
    id: 'decision-tools',
    label: 'Decision Tools',
    kicker: 'Applied analysis',
    title: 'Turn analysis into roster decisions',
    description: 'Build practical tools for comparing options, evaluating moves, and testing team construction.',
    sections: [
      {
        eyebrow: '01 · Compare',
        title: 'Player comparisons',
        description: 'Make side-by-side evaluation deeper, faster, and easier to share.',
        items: [
          'Compare players across seasons, roles, contracts, and advanced metrics',
          'Find similar players and comparable career paths',
          'Save, share, and export comparison views',
        ],
      },
      {
        eyebrow: '02 · Evaluate',
        title: 'Trade analysis',
        description: 'Measure the performance, contract, and cap consequences on both sides of a move.',
        items: [
          'Estimate trade value and evaluate multi-player scenarios',
          'Compare immediate value, future projection, contract efficiency, and risk',
          'Include team context and future cap implications',
        ],
      },
      {
        eyebrow: '03 · Build',
        title: 'Roster building & team fit',
        description: 'Test how a player fits a role, system, budget, and competitive window.',
        items: [
          'Model roster and salary-cap scenarios across multiple seasons',
          'Assess fit by position, role, playing style, teammates, and cost',
          'Compare free-agent and internal roster alternatives',
        ],
      },
    ],
  },
  {
    id: 'platform',
    label: 'Platform',
    kicker: 'Product foundation',
    title: 'Make the platform faster and more useful',
    description: 'Improve how the product performs, adapts, and makes its data available to others.',
    sections: [
      {
        eyebrow: '01 · Experience',
        title: 'Performance & access',
        description: 'Keep the experience quick and clear on every device.',
        items: [
          'Connect every production page to live data and improve loading performance',
          'Strengthen mobile and tablet layouts and continue accessibility improvements',
          'Expand global search, page-level filtering, and personalized saved views',
        ],
      },
      {
        eyebrow: '02 · Reliability',
        title: 'Monitoring & automated testing',
        description: 'Catch regressions in the website, API, database, pipelines, and models.',
        items: [
          'Add service health, runtime, pipeline, and data-quality monitoring',
          'Expand automated tests and deployment checks across the stack',
          'Make failures actionable with clear alerts and recovery paths',
        ],
      },
      {
        eyebrow: '03 · Portability',
        title: 'Exports & public API access',
        description: 'Let analysts and builders use stable TradeValue data in their own work.',
        items: [
          'Offer downloadable tables and shareable analytical views',
          'Define stable, documented export formats',
          'Provide public API access where data rights and reliability allow it',
        ],
      },
    ],
  },
  {
    id: 'timeline',
    label: 'Timeline',
    kicker: 'Development order',
    title: 'Build the foundation before the forecast',
    description: 'The sequence prioritizes trustworthy live data first, deeper NHL analysis second, and cross-league intelligence third.',
    sections: [
      {
        eyebrow: 'Now · Near term',
        title: 'Reliable live product',
        description: 'Complete the data foundation and strengthen the experience already in production.',
        items: [
          'Connect live production data across the site',
          'Automate NHL collection, validation, freshness reporting, and pipeline monitoring',
          'Improve player, team, contract, and comparison pages with existing data',
          'Publish definitions for Hockey Value and other calculated metrics',
        ],
      },
      {
        eyebrow: 'Next · Medium term',
        title: 'Models & deeper analysis',
        description: 'Turn richer NHL event data into projections and practical decision tools.',
        items: [
          'Add play-by-play, shot-location, and game-level data',
          'Release shot maps, trends, and deeper team analytics',
          'Build player growth, regression, salary, and contract-value models',
          'Add team, standings, and game prediction models plus improved cap scenarios',
        ],
      },
      {
        eyebrow: 'Later · Long term',
        title: 'Connected hockey careers',
        description: 'Extend the system beyond the NHL and model the full development path.',
        items: [
          'Add AHL, NCAA, major junior, and other lower-level statistics',
          'Connect identities and career histories across leagues',
          'Build league-adjusted metrics and NHL-equivalency models',
          'Use full career histories in prospect, growth, salary, and valuation models',
        ],
      },
    ],
  },
]

const defaultTab = tabs[0]

export function FuturePlansPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([])
  const requestedTab = searchParams.get('tab')
  const activeTab = tabs.find((tab) => tab.id === requestedTab) ?? defaultTab
  const activeIndex = tabs.indexOf(activeTab)

  const selectTab = (id: string) => {
    const nextParams = new URLSearchParams(searchParams)
    nextParams.set('tab', id)
    setSearchParams(nextParams)
  }

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextIndex: number | undefined
    if (event.key === 'ArrowRight') nextIndex = (index + 1) % tabs.length
    if (event.key === 'ArrowLeft') nextIndex = (index - 1 + tabs.length) % tabs.length
    if (event.key === 'Home') nextIndex = 0
    if (event.key === 'End') nextIndex = tabs.length - 1
    if (nextIndex === undefined) return

    event.preventDefault()
    selectTab(tabs[nextIndex].id)
    tabRefs.current[nextIndex]?.focus()
  }

  return <div className="future-plans-page">
    <div className="plans-summary" aria-label="Roadmap summary">
      <div><span>Current focus</span><strong>Data automation</strong></div>
      <div><span>Roadmap areas</span><strong>{tabs.length}</strong></div>
      <div><span>Guiding principle</span><strong>Transparent by design</strong></div>
    </div>

    <div className="plans-workspace">
      <div className="plans-tabs-scroll">
        <div className="plans-tabs" role="tablist" aria-label="Future plans categories">
          {tabs.map((tab, index) => <button
            key={tab.id}
            ref={(element) => { tabRefs.current[index] = element }}
            id={`tab-${tab.id}`}
            type="button"
            role="tab"
            aria-selected={tab.id === activeTab.id}
            aria-controls={`panel-${tab.id}`}
            tabIndex={tab.id === activeTab.id ? 0 : -1}
            onClick={() => selectTab(tab.id)}
            onKeyDown={(event) => handleTabKeyDown(event, index)}
          >{tab.label}</button>)}
        </div>
      </div>

      <section
        key={activeTab.id}
        id={`panel-${activeTab.id}`}
        className="plans-panel"
        role="tabpanel"
        aria-labelledby={`tab-${activeTab.id}`}
        tabIndex={0}
      >
        <header className="plans-panel-header">
          <div><span>{activeTab.kicker}</span><h2>{activeTab.title}</h2></div>
          <p>{activeTab.description}</p>
          <strong aria-label={`${activeTab.sections.length} workstreams`}>{String(activeIndex + 1).padStart(2, '0')} / {String(tabs.length).padStart(2, '0')}</strong>
        </header>

        <div className={`plans-section-grid plans-section-grid-${activeTab.sections.length}`}>
          {activeTab.sections.map((section) => <article className="plan-card" key={section.title}>
            <header><span>{section.eyebrow}</span><h3>{section.title}</h3><p>{section.description}</p></header>
            <ul>{section.items.map((item) => <li key={item}>{item}</li>)}</ul>
          </article>)}
        </div>
      </section>
    </div>

    <section className="plans-contribute" aria-labelledby="plans-contribute-title">
      <div><span>Open collaboration</span><h2 id="plans-contribute-title">Help shape what comes next</h2></div>
      <p>Developers, analysts, and hockey fans can contribute data ideas, modeling experience, product feedback, or code.</p>
      <a href="mailto:cillieevan@gmail.com?subject=TradeValue%20contribution">Start a conversation <span aria-hidden="true">↗</span></a>
    </section>

    <p className="plans-disclaimer">This roadmap reflects the current direction of TradeValue. Priorities may change as new data becomes available, the platform grows, and contributors bring new ideas to the project.</p>
  </div>
}
