import { PageHeader } from '../components/common/PageHeader'

const features = [
  'Player profiles',
  'Team rosters',
  'Contract information',
  'Season history',
  'League leaderboards',
  'Player comparisons',
]

const background = [
  'Combining experience in hockey, software engineering, economics, and data analysis',
  'Three years with Union College men\'s hockey',
  'Degrees in computer science and economics',
  'Software engineer focused on automation and machine learning',
]

export function AboutPage() {
  return <div className="about-page">
    <PageHeader
      eyebrow="The story behind the data"
      title="About TradeValue"
      description="Hockey performance, contracts, and salary-cap value—connected in one place."
    />

    <div className="about-grid">
      <section className="about-card" aria-labelledby="about-project">
        <header><span>01 · The project</span><h2 id="about-project">Built for better hockey questions</h2></header>
        <p>TradeValue brings player performance, advanced statistics, contracts, salary-cap information, and player valuation together. It makes hockey data easier to explore and shows how on-ice performance relates to a player's contract and value to a team.</p>
        <ul className="about-feature-list" aria-label="Current features">
          {features.map((feature) => <li key={feature}>{feature}</li>)}
        </ul>
        <aside className="about-source-note"><strong>Public data</strong><span>NHL, MoneyPuck, CapWages, and AHL HockeyTech / LeagueStat help make this independent analysis possible.</span></aside>
      </section>

      <section className="about-card" aria-labelledby="about-evan">
        <header><span>02 · The creator</span><h2 id="about-evan">Evan Cillie</h2></header>
        <p>TradeValue combines Evan's background in hockey, economics, software engineering, and data analysis. He has played competitive hockey since age four, spent three years with Union College's NCAA men's hockey team, and graduated from Union with degrees in computer science and economics.</p>
        <ul className="about-background" aria-label="Evan Cillie's background">
          {background.map((item) => <li key={item}>{item}</li>)}
        </ul>
        <nav className="about-links" aria-label="Evan Cillie links">
          <a href="https://evan-cillie.vercel.app/" target="_blank" rel="noreferrer">Website <span>↗</span></a>
          <a href="https://www.linkedin.com/in/evan-cillie" target="_blank" rel="noreferrer">LinkedIn <span>↗</span></a>
          <a href="https://github.com/ecillie/Hockey-Analytics" target="_blank" rel="noreferrer">GitHub <span>↗</span></a>
        </nav>
      </section>

      <section className="about-contribute" aria-labelledby="about-contribute">
        <div><span>Open collaboration</span><h2 id="about-contribute">Contribute</h2></div>
        <p>Developers, analysts, and hockey fans are welcome. Reach out by email with your background, interests, and ideas for the platform.</p>
        <a href="mailto:cillieevan@gmail.com">cillieevan@gmail.com <span>↗</span></a>
      </section>
    </div>
  </div>
}
