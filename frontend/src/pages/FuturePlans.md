# Future Plans

Hockey Analytics is being built into a broader platform for exploring player performance, contracts, team construction, and the factors that shape results across professional and developmental hockey. The long-term goal is to make advanced hockey data easier to understand while creating models that can answer practical questions about player value, future performance, and team success.

This roadmap reflects the current direction of the project. Priorities may change as new data becomes available, the platform grows, and contributors bring new ideas to the project.

## Web-App Layout

The Future Plans page should be built as an interactive tabbed view within the web app. Selecting a tab should update the content panel without reloading the page. Each tab should also have its own URL state, such as `/future-plans?tab=player-analytics`, so users can bookmark and share a specific section. Opening the main `/future-plans` route should display Data & Automation by default.

The interface should include the following tabs:

### Data & Automation

- Automated Data Updates
- Broader Hockey Data
- Model Transparency and Data Quality

### Player Analytics

- Deeper Player Analytics
- Player Growth and Regression Models

### Contracts & Salary

- Salary and Contract Models
- Contract-risk analysis
- Comparable-contract analysis

### Teams & Games

- Team Analytics and Salary-Cap Tools
- Game-by-Game Analysis and Predictions

### Decision Tools

- Player comparisons
- Trade analysis
- Roster-building tools
- Team-fit analysis

### Platform

- Performance and loading improvements
- Mobile and tablet support
- Search and filtering
- Monitoring and automated testing
- Data exports and public API access

### Timeline

- Near-term priorities
- Medium-term priorities
- Long-term priorities

Only the selected tab's content should appear in the main panel. The active tab should be visually clear, and changing tabs should preserve the user's position on the page. The browser's Back and Forward buttons should move between previously selected tabs.

On desktop, display the tabs in a single navigation row when space allows. On mobile and smaller screens, use a horizontally scrollable tab row or a dropdown selector. Tab controls must support keyboard navigation, visible focus states, screen readers, and standard accessible tab roles.

The Contribute call to action should remain visible below the tab panel so visitors can always find information about joining the project. The disclaimer should appear at the bottom of the page outside the tabbed content.

## Automated Data Updates

The first priority is building a reliable system that keeps the platform current without requiring manual updates. Scheduled data pipelines will collect and refresh player statistics, advanced metrics, contracts, roster statuses, schedules, game results, and salary-cap information.

Planned work includes:

- Schedule automatic updates throughout the NHL season
- Refresh player, team, contract, roster, schedule, and game data
- Validate new data before it is published to the site
- Detect missing, duplicated, incomplete, or unexpected records
- Monitor pipeline failures and send alerts when an update does not complete
- Display when each dataset was last updated
- Preserve historical snapshots of contracts, rosters, and player performance
- Build recovery processes that can safely rerun failed updates

## Broader Hockey Data

The platform currently focuses on NHL data. Future versions will connect player performance across professional and developmental leagues to provide a more complete view of each player's career.

Planned leagues and levels include:

- American Hockey League (AHL)
- NCAA men's hockey
- Canadian major junior hockey
- Other professional and development leagues where reliable data is available

Planned features include:

- Career histories that connect the same player across leagues and teams
- AHL, NCAA, and junior player statistics
- Prospect profiles and development timelines
- League-adjusted metrics for comparing production across different levels
- NHL-equivalency models that estimate how lower-level production may translate to the NHL
- Development-league performance as an input to player projections and valuations
- Tracking prospects from their pre-NHL careers through their professional development

## Deeper Player Analytics

Player pages will expand beyond traditional season totals to provide a clearer view of how a player creates value and how that value changes over time.

Planned additions include:

- Play-by-play and game-by-game performance
- Shot locations and interactive shot maps
- Expected goals and scoring-chance analysis
- On-ice possession and territorial metrics
- Even-strength, power-play, and penalty-kill splits
- Teammate, opponent, and usage context
- Line combinations and defensive pairings
- Rolling performance trends
- Player similarity and comparable-player tools
- Age curves and career development profiles
- Separate analytical views for forwards, defensemen, and goaltenders

## Player Growth and Regression Models

Future models will estimate how player performance is likely to change rather than relying only on past results. These models will account for age, position, role, ice time, league history, recent performance, and comparable career paths.

Planned outputs include:

- Next-season performance projections
- Multi-season development forecasts
- Expected peak age and peak performance
- Breakout probability
- Decline and regression probability
- Expected changes in role and ice time
- Confidence ranges that show the uncertainty around each projection
- Separate models for forwards, defensemen, and goaltenders
- In-season updates as new games are played

Model pages will explain the most important factors behind each projection and publish performance metrics so users can evaluate how accurate the models are over time.

## Salary and Contract Models

The platform will build on its player-value work to estimate what a player's performance should be worth in the NHL salary-cap environment.

Planned features include:

- Expected salary and cap-hit predictions
- Fair contract value based on projected future performance
- Contract-term recommendations
- Comparable-contract analysis
- Estimates for unrestricted and restricted free agents
- Surplus-value and negative-value contract estimates
- Historical comparisons that adjust for changes in the salary cap
- Contract-risk estimates based on age, term, injuries, and projected regression
- Team-level views of contract efficiency and long-term commitments

Salary predictions will distinguish between a player's projected on-ice value and the market factors that influence actual NHL contracts.

## Team Analytics and Salary-Cap Tools

Team pages will grow into complete views of roster construction, performance, and financial flexibility.

Planned additions include:

- Team-level traditional and advanced statistics
- Roster strengths and weaknesses by position
- Lineup and depth-chart views
- Team shot maps and scoring profiles
- Special-teams analysis
- Contract ledgers and multi-year cap commitments
- Projected cap space
- Long-term injured reserve and buried-contract calculations
- Accrued cap-space estimates
- Roster and contract scenario tools
- Team performance projections
- Standings and playoff-probability models

## Game-by-Game Analysis and Predictions

Game pages will combine schedule information, recent performance, expected lineups, goaltending, and team-level analytics.

Planned features include:

- Game previews and matchup comparisons
- Win-probability predictions
- Expected scoring for each team
- Projected starting-goaltender impact
- Recent-form and rest-day context
- Home, away, travel, and schedule effects
- In-game win probability when reliable live data is available
- Postgame summaries showing what drove the result
- Model accuracy tracking throughout the season

Predictions will update as new information becomes available and will include clear explanations of the data and assumptions behind them.

## Comparison and Decision Tools

The existing player comparison experience will grow into a set of tools for evaluating players, contracts, and roster decisions.

Planned tools include:

- Expanded player comparisons across seasons and metrics
- Similar-player search
- Contract comparisons
- Trade-value analysis
- Trade scenario evaluation
- Free-agent comparisons
- Roster-building and salary-cap scenarios
- Team fit analysis based on role, position, playing style, and cost
- Downloadable tables and shareable comparison views

## Model Transparency and Data Quality

Every model and dataset should be understandable and testable. The platform will document where its data comes from, how each metric is calculated, and how predictive models perform.

Planned work includes:

- Metric definitions and methodology pages
- Data-source acknowledgments
- Model version and training-date information
- Accuracy reports and historical backtesting
- Clear separation between recorded statistics, calculated metrics, and predictions
- Confidence ranges for forecasts
- Data-freshness indicators
- Known limitations and missing-data notes
- Automated tests for data pipelines, APIs, and model outputs

## Platform Improvements

The technical platform will continue to improve alongside the analytics.

Planned work includes:

- Connect all production pages to live data
- Improve performance and loading times
- Strengthen mobile and tablet support
- Expand search and filtering
- Add saved comparisons and personalized views
- Improve accessibility
- Add monitoring for the website, API, database, and data pipelines
- Expand automated testing and deployment checks
- Provide stable exports or public API access where appropriate

## Suggested Development Order

### Near Term

1. Complete the live production data connection across the site.
2. Automate NHL data collection and validation.
3. Add visible data-freshness information and pipeline monitoring.
4. Improve player, team, contract, and comparison pages using the existing data.
5. Publish clear definitions for Hockey Value and other calculated metrics.

### Medium Term

1. Add play-by-play data, shot locations, and game-by-game statistics.
2. Build shot maps, performance trends, and deeper team analytics.
3. Release player growth, regression, salary, and contract-value models.
4. Add team performance, standings, and game prediction models.
5. Improve salary-cap calculations and scenario tools.

### Long Term

1. Add AHL, NCAA, major junior, and other lower-level statistics.
2. Connect player identities and career histories across leagues.
3. Build league-adjusted metrics and NHL-equivalency models.
4. Use full career histories in prospect, growth, salary, and valuation models.
5. Develop advanced trade, roster-building, and team-fit tools.

## Contribute

Hockey Analytics is an independent project, and contributions from developers, analysts, designers, and hockey fans are welcome. Potential contributors can help with data collection, validation, modeling, backend development, frontend features, design, testing, or hockey research.

If you are interested in contributing, email [cillieevan@gmail.com](mailto:cillieevan@gmail.com) with a short introduction, your interests, and how you would like to help.

You can also learn more about the project and its creator through the following links:

- [Hockey Analytics repository](https://github.com/ecillie/hockey-analytics)
- [Evan Cillie's personal website](https://evan-cillie.vercel.app/)
- LinkedIn

## Disclaimer

Hockey Analytics is an independent project and is not affiliated with the NHL, AHL, NCAA, MoneyPuck, CapWages, or their respective teams and organizations. Features described on this page are planned work and may change as the project develops.