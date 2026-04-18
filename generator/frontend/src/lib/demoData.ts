import type { WidgetData } from './renderWidgets'

// Used to show a fully-populated Workshop preview instantly while the real
// data is building asynchronously on the server. Swapped out when the
// /data endpoint returns status=ready.
export const DEMO_WIDGET_DATA: WidgetData = {
  grade: {
    grade: 'A',
    score: 78,
    stats: { commits: 842, prs: 47, stars: 156, repos: 28, followers: 92 },
    tags: [
      { tag: 'backend', source: 'earned', confidence: 0.7 },
      { tag: 'frontend', source: 'earned', confidence: 0.55 },
      { tag: 'devops', source: 'earned', confidence: 0.3 },
    ],
    breakdown: {},
  },
  impact: Array.from({ length: 24 }, (_, i) => ({
    week_start: new Date(Date.now() - (23 - i) * 7 * 86400000).toISOString().slice(0, 10),
    commits: Math.max(0, Math.round(14 + Math.sin(i * 0.5) * 9 + (i % 3) * 2)),
  })),
  collaborators: [
    { username: 'alex', shared_repos: 4, shared_commits: 87 },
    { username: 'jordan', shared_repos: 2, shared_commits: 54 },
    { username: 'sam', shared_repos: 3, shared_commits: 31 },
  ],
  focus: [
    { category: 'Backend', percentage: 45, commit_count: 379 },
    { category: 'Frontend', percentage: 30, commit_count: 252 },
    { category: 'DevOps', percentage: 15, commit_count: 126 },
    { category: 'ML', percentage: 10, commit_count: 84 },
  ],
  languages: [
    { language: 'Python', percentage: 42, loc: 12 },
    { language: 'TypeScript', percentage: 28, loc: 8 },
    { language: 'Go', percentage: 18, loc: 5 },
    { language: 'Rust', percentage: 12, loc: 3 },
  ],
}
