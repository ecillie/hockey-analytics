import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { api } from './api'
import { mockContracts, mockHistory, mockPlayerStats, mockPlayers, mockTeams } from './mocks/fixtures'

afterEach(() => vi.restoreAllMocks())

const renderAt = (path: string) => {
  window.history.pushState({}, '', path)
  return render(<App />)
}

describe('application routes', () => {
  it('renders the overview and changes season', async () => {
    const user = userEvent.setup()
    renderAt('/')
    expect(await screen.findByRole('heading', { name: 'NHL Overview' })).toBeInTheDocument()
    await screen.findByRole('option', { name: '2024–25' })
    await user.selectOptions(screen.getByLabelText('Season'), '2024')
    expect(screen.getByLabelText('Season')).toHaveValue('2024')
  })

  it('searches and filters the player list through URL state', async () => {
    const user = userEvent.setup()
    renderAt('/players')
    expect(await screen.findByRole('heading', { name: 'Players' })).toBeInTheDocument()
    const inputs = screen.getAllByPlaceholderText('Player name')
    await user.type(inputs[0], 'McDavid')
    await screen.findByText('1 players')
    expect(screen.getByText('Connor McDavid')).toBeInTheDocument()
    expect(screen.queryByText('Nathan MacKinnon')).not.toBeInTheDocument()
  })

  it('renders player detail, team navigation, and comparison routes', async () => {
    const { unmount } = renderAt('/players/101')
    expect(await screen.findByRole('heading', { name: 'Connor McDavid' })).toBeInTheDocument()
    expect(await screen.findByText('Next-season projection')).toBeInTheDocument()
    unmount()
    window.history.pushState({}, '', '/teams/11')
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Edmonton Oilers' })).toBeInTheDocument()
    expect(await screen.findByText('Contract ledger')).toBeInTheDocument()
  })

  it('renders empty and API error states', async () => {
    const { unmount } = renderAt('/players?search=doesnotexist')
    expect(await screen.findByText('No players found')).toBeInTheDocument()
    unmount()
    window.history.pushState({}, '', '/players?search=__error__')
    render(<App />)
    await waitFor(() => expect(screen.getByText('Unable to load player statistics.')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('renders a not-found route', async () => {
    renderAt('/missing')
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument()
  })

  it('renders the about page content and profile links', async () => {
    renderAt('/about')
    expect(await screen.findByRole('heading', { name: 'About TradeValue' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Built for better hockey questions' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Evan Cillie' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Contribute' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Website/ })).toHaveAttribute('href', 'https://evan-cillie.vercel.app/')
    expect(screen.getByRole('link', { name: /LinkedIn/ })).toHaveAttribute('href', 'https://www.linkedin.com/in/evan-cillie')
    expect(screen.getByRole('link', { name: /GitHub/ })).toHaveAttribute('href', 'https://github.com/ecillie/Hockey-Analytics')
    expect(screen.getByRole('link', { name: /cillieevan@gmail.com/ })).toHaveAttribute('href', 'mailto:cillieevan@gmail.com')
  })

  it('renders and navigates the future plans roadmap', async () => {
    const user = userEvent.setup()
    renderAt('/future-plans')
    expect(await screen.findByRole('tab', { name: 'Data & Automation' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('heading', { name: 'A reliable data engine' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Deeper player analytics' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Help shape what comes next' })).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Player Analytics' }))
    expect(window.location.search).toBe('?tab=player-analytics')
    expect(screen.getByRole('tab', { name: 'Player Analytics' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('heading', { name: 'Deeper player analytics' })).toBeInTheDocument()

    await user.keyboard('{End}')
    expect(window.location.search).toBe('?tab=timeline')
    expect(screen.getByRole('tab', { name: 'Timeline' })).toHaveFocus()
    expect(screen.getByRole('heading', { name: 'Reliable live product' })).toBeInTheDocument()

    window.history.back()
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Player Analytics' })).toHaveAttribute('aria-selected', 'true'))
    expect(screen.getByRole('heading', { name: 'Deeper player analytics' })).toBeInTheDocument()

    window.history.forward()
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Timeline' })).toHaveAttribute('aria-selected', 'true'))
    expect(screen.getByRole('heading', { name: 'Reliable live product' })).toBeInTheDocument()
  })

  it('opens a shared future plans tab from the URL', async () => {
    renderAt('/future-plans?tab=teams-games')
    expect(await screen.findByRole('tab', { name: 'Teams & Games' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('heading', { name: 'Team analytics & salary-cap tools' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Automated data updates' })).not.toBeInTheDocument()
  })

  it('supports complete keyboard navigation and invalid tab fallbacks', async () => {
    const user = userEvent.setup()
    renderAt('/future-plans?tab=not-a-roadmap-tab')

    const dataTab = await screen.findByRole('tab', { name: 'Data & Automation' })
    expect(dataTab).toHaveAttribute('aria-selected', 'true')
    dataTab.focus()

    await user.keyboard('{ArrowLeft}')
    expect(screen.getByRole('tab', { name: 'Timeline' })).toHaveFocus()
    expect(window.location.search).toBe('?tab=timeline')

    await user.keyboard('{ArrowRight}')
    expect(dataTab).toHaveFocus()
    expect(window.location.search).toBe('?tab=data-automation')

    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: 'Player Analytics' })).toHaveFocus()
    await user.keyboard('{ArrowLeft}')
    expect(dataTab).toHaveFocus()

    await user.keyboard('{End}')
    expect(screen.getByRole('tab', { name: 'Timeline' })).toHaveFocus()
    await user.keyboard('{Home}')
    expect(dataTab).toHaveFocus()

    const unchangedUrl = window.location.href
    await user.keyboard('{PageDown}')
    expect(window.location.href).toBe(unchangedUrl)
    expect(dataTab).toHaveFocus()
  })

  it('renders every roadmap category with accessible, persistent URL state', async () => {
    const user = userEvent.setup()
    renderAt('/future-plans?tab=platform&source=shared-roadmap')

    const categories = [
      ['Data & Automation', 'Automated data updates'],
      ['Player Analytics', 'Deeper player analytics'],
      ['Contracts & Salary', 'Salary & contract models'],
      ['Teams & Games', 'Team analytics & salary-cap tools'],
      ['Decision Tools', 'Player comparisons'],
      ['Platform', 'Performance & access'],
      ['Timeline', 'Reliable live product'],
    ] as const

    expect(await screen.findByRole('heading', { name: 'Performance & access' })).toBeInTheDocument()
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', 'tab-platform')

    for (const [tabName, sectionHeading] of categories) {
      const tab = screen.getByRole('tab', { name: tabName })
      await user.click(tab)
      expect(tab).toHaveAttribute('aria-selected', 'true')
      expect(tab).toHaveAttribute('tabindex', '0')
      expect(screen.getByRole('tabpanel')).toHaveAttribute('id', tab.getAttribute('aria-controls'))
      expect(screen.getByRole('heading', { name: sectionHeading })).toBeInTheDocument()
      expect(window.location.search).toContain('source=shared-roadmap')
      expect(screen.getAllByRole('tabpanel')).toHaveLength(1)
    }

    expect(screen.getByRole('link', { name: 'Start a conversation' })).toHaveAttribute(
      'href',
      'mailto:cillieevan@gmail.com?subject=TradeValue%20contribution',
    )
    expect(screen.getByText(/This roadmap reflects the current direction of TradeValue/)).toBeInTheDocument()
    expect(screen.getAllByRole('tab').filter((tab) => tab.getAttribute('aria-selected') === 'true')).toHaveLength(1)
  })

  it('filters, sorts, paginates, and resets the player directory', async () => {
    const user = userEvent.setup()
    renderAt('/players')
    await screen.findByRole('heading', { name: 'Players' })
    await screen.findByRole('option', { name: /EDM/ })
    await new Promise((resolve) => window.setTimeout(resolve, 350))
    await user.selectOptions(screen.getByLabelText('Team'), 'EDM')
    expect(screen.getByLabelText('Team')).toHaveValue('EDM')
    await user.selectOptions(screen.getByLabelText('Team'), '')
    await user.selectOptions(screen.getByLabelText('Season'), '2024')
    await user.selectOptions(screen.getByLabelText('Position'), 'C')
    await user.selectOptions(screen.getByLabelText('Roster'), 'ACTIVE')
    await user.click(screen.getByRole('button', { name: /HV/ }))
    expect(await screen.findByText(/Sorted by hockeyValue/)).toHaveTextContent('asc')
    await user.click(screen.getByRole('button', { name: 'PTS' }))
    expect(await screen.findByText(/Sorted by points/)).toHaveTextContent('desc')
    await user.click(screen.getByRole('button', { name: 'Reset' }))
    expect(screen.getByLabelText('Team')).toHaveValue('')
    await screen.findByText('22 players')
    await user.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('22 results · Page 2 of 3')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Previous' }))
    expect(await screen.findByText('22 results · Page 1 of 3')).toBeInTheDocument()
  }, 10_000)

  it('lists teams and follows a team link', async () => {
    const user = userEvent.setup()
    renderAt('/teams')
    expect(await screen.findByRole('heading', { name: 'Teams' })).toBeInTheDocument()
    await user.click((await screen.findByText('Edmonton Oilers')).closest('a')!)
    expect(await screen.findByRole('heading', { name: 'Edmonton Oilers' })).toBeInTheDocument()
  })

  it('adds and removes comparison players with two-to-four enforcement', async () => {
    const user = userEvent.setup()
    renderAt('/compare')
    expect(await screen.findByRole('heading', { name: 'Player comparison' })).toBeInTheDocument()
    expect(await screen.findByRole('row', { name: /Hockey Value/ })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Connor McDavid/ }))
    expect(await screen.findByText('Select at least two players.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await user.click(screen.getByRole('button', { name: /Connor McDavid/ }))
    expect(await screen.findByRole('row', { name: /Projected HV/ })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Auston Matthews/ }))
    await user.click(screen.getByRole('button', { name: /Cale Makar/ }))
    expect(screen.getByRole('button', { name: /Leon Draisaitl/ })).toBeDisabled()
  }, 10_000)

  it('retries a failed overview request', async () => {
    const getOverview = vi.spyOn(api, 'getOverview').mockRejectedValueOnce(new Error('offline'))
    const user = userEvent.setup()
    renderAt('/')
    expect(await screen.findByText('Unable to load the league overview.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByLabelText('League snapshot')
    expect(getOverview).toHaveBeenCalledTimes(2)
  })

  it('renders directory, player, and team failures', async () => {
    vi.spyOn(api, 'getTeams').mockRejectedValueOnce(new Error('offline'))
    const { unmount } = renderAt('/teams')
    expect(await screen.findByText('Unable to load teams.')).toBeInTheDocument()
    unmount()
    window.history.pushState({}, '', '/players/99999')
    render(<App />)
    expect(await screen.findByText('Unable to load this player.')).toBeInTheDocument()
  })

  it('renders goalie, missing contract, and season-stat error branches', async () => {
    vi.spyOn(api, 'getPlayerContract').mockResolvedValueOnce(null)
    const { unmount } = renderAt('/players/120')
    expect(await screen.findByRole('heading', { name: 'Carey Price' })).toBeInTheDocument()
    expect(await screen.findByText('No active contract is available.')).toBeInTheDocument()
    expect(screen.getByText('Advanced skater statistics are not available.')).toBeInTheDocument()
    unmount()
    vi.spyOn(api, 'getPlayerStats').mockRejectedValueOnce(new Error('bad stats'))
    window.history.pushState({}, '', '/players/101')
    render(<App />)
    expect(await screen.findByText('Unable to load season statistics.')).toBeInTheDocument()
  })

  it('renders team roster and contract errors and retries them', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'getTeamRoster').mockRejectedValueOnce(new Error('bad roster'))
    vi.spyOn(api, 'getTeamContracts').mockRejectedValueOnce(new Error('bad contracts'))
    renderAt('/teams/11')
    expect(await screen.findByText('Unable to load the roster.')).toBeInTheDocument()
    expect(await screen.findByText('Unable to load team contracts.')).toBeInTheDocument()
    const retries = screen.getAllByRole('button', { name: 'Try again' })
    await user.click(retries[0])
    await user.click(retries[1])
    expect(await screen.findByRole('table', { name: '' }).catch(() => null)).not.toBeNull()
    expect(await screen.findByText(/contracts/)).toBeInTheDocument()
  })

  it('renders a missing team and generic comparison failure', async () => {
    const { unmount } = renderAt('/teams/99999')
    expect(await screen.findByText('Unable to load this team.')).toBeInTheDocument()
    unmount()
    vi.spyOn(api, 'comparePlayers').mockRejectedValueOnce(new Error('bad comparison'))
    window.history.pushState({}, '', '/compare?ids=101,102')
    render(<App />)
    expect(await screen.findByText('Unable to build this comparison.')).toBeInTheDocument()
  })

  it('renders defensive player fallbacks and pending detail sections', async () => {
    let resolveStats!: (value: typeof mockPlayerStats[101]) => void
    let resolveContract!: (value: typeof mockContracts[101]) => void
    let resolveHistory!: (value: typeof mockHistory[101]) => void
    vi.spyOn(api, 'getPlayer').mockResolvedValue({ ...mockPlayers[0], team: null, primaryPosition: null, age: null, shootsCatches: null, nationality: null })
    vi.spyOn(api, 'getPlayerStats').mockReturnValue(new Promise((resolve) => { resolveStats = resolve }))
    vi.spyOn(api, 'getPlayerSeasons').mockReturnValue(new Promise((resolve) => { resolveHistory = resolve }))
    vi.spyOn(api, 'getPlayerContract').mockReturnValue(new Promise((resolve) => { resolveContract = resolve }))
    renderAt('/players/101')
    expect(await screen.findByRole('heading', { name: 'Connor McDavid' })).toBeInTheDocument()
    expect(screen.getByText('Team unavailable · Position unavailable')).toBeInTheDocument()
    expect(screen.getAllByLabelText('Loading').length).toBeGreaterThan(0)
    await screen.findByText('Current value')
    resolveStats({ ...mockPlayerStats[101], advanced: { ...mockPlayerStats[101].advanced!, penalties: null, penaltiesDrawn: null } })
    resolveContract({ ...mockContracts[101], expiryStatus: null })
    resolveHistory([{ ...mockHistory[101][0], team: null }])
    expect(await screen.findByText('Penalty differential')).toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('renders comparison and team fallbacks from partial API data', async () => {
    const comparison = await api.comparePlayers([101, 102], 2025)
    comparison.players[0] = { ...comparison.players[0], stats: { ...comparison.players[0].stats, advanced: null } }
    vi.spyOn(api, 'comparePlayers').mockResolvedValue(comparison)
    const { unmount } = renderAt('/compare?ids=101,102')
    expect(await screen.findByRole('row', { name: /On-ice xG share/ })).toHaveTextContent('0.0%')
    unmount()

    vi.spyOn(api, 'getTeam').mockResolvedValue({ ...mockTeams[10], city: null, rosterCounts: { ACTIVE: undefined, MINORS: 0, LTIR: 0, UNKNOWN: 0 } as never })
    vi.spyOn(api, 'getTeamCap').mockResolvedValue({ teamId: 11, season: 2025, salaryCapCents: null, activeRosterCapCents: 0, ltirCapCents: 0, minorsCapCents: 0, totalCommitmentsCents: 0, capSpaceCents: -1, calculationStatus: 'AUTHORITATIVE' })
    vi.spyOn(api, 'getTeamRoster').mockResolvedValue(undefined as never)
    window.history.pushState({}, '', '/teams/11')
    render(<App />)
    expect(await screen.findByText('Authoritative calculation')).toBeInTheDocument()
    expect(screen.getByText('Projected space').nextElementSibling).toHaveClass('negative')
    expect(screen.getByText('No players found')).toBeInTheDocument()
  })

  it('uses zero when team cap space is unavailable', async () => {
    vi.spyOn(api, 'getTeamCap').mockResolvedValue({ teamId: 11, season: 2025, salaryCapCents: null, activeRosterCapCents: 0, ltirCapCents: 0, minorsCapCents: 0, totalCommitmentsCents: 0, capSpaceCents: null, calculationStatus: 'ESTIMATE' })
    renderAt('/teams/11')
    expect(await screen.findByText('Development estimate — backend cap engine required')).toBeInTheDocument()
    expect(screen.getByText('Projected space').nextElementSibling).toHaveClass('positive')
  })
})
