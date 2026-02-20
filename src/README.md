# GitHub Profile Widget Generator

A modular system for generating polished SVG widgets from GitHub profile data.

## Project Structure

```
src/
├── models/              # Data classes and types
│   ├── __init__.py
│   └── types.py         # Widget data models
│
├── themes/              # Color schemes and styling
│   ├── __init__.py
│   └── themes.py        # Theme definitions
│
├── widgets/             # Widget rendering modules
│   ├── __init__.py
│   ├── grade.py         # Developer grade widget
│   ├── impact.py        # Impact timeline chart
│   ├── collaborators.py # Top collaborators
│   ├── focus.py         # Focus areas bars
│   ├── languages.py     # Languages donut chart
│   ├── achievements.py  # Achievements list
│   └── composite.py     # Full widget composer
│
├── data/                # Data fetching and processing
│   ├── __init__.py
│   ├── fetcher.py       # GitHub API client
│   └── processor.py     # Data transformation
│
├── utils/               # Helper functions
│   ├── __init__.py
│   └── svg_helpers.py   # SVG utilities
│
└── generate.py          # Main CLI entry point
```

## Usage

Run from the project root directory:

```bash
# Generate widgets for a user
python run.py <username> [theme]

# Or run as a module
python -m src.generate <username> [theme]

# With GitHub token for higher rate limits
GITHUB_TOKEN=your_token python run.py <username>

# Use light theme
python run.py <username> light
```

## Extending

### Adding a New Widget

1. Create a new file in `widgets/` (e.g., `widgets/my_widget.py`)
2. Implement `render_my_widget(data, theme_name="dark") -> str`
3. Add to `widgets/__init__.py` exports
4. Update `data/processor.py` to include it in `generate_widgets_from_github()`

### Adding a New Theme

1. Add theme definition to `themes/themes.py`
2. Use the theme name when calling `generate_full_widget(theme="my_theme")`

## Configuration

Customize behavior via environment variables:

```bash
# Collaborator settings
export COLLABORATOR_MIN_COMMITS=10        # Min commits to be a collaborator (default: 10)
export COLLABORATOR_MAX_REPO_SIZE=100     # Skip repos with 100+ contributors (default: 100)
export COLLABORATOR_TOP_REPOS=5           # Check top N repos for collaborators (default: 5)

# Commit fetching
export COMMIT_MAX_REPOS=10                # Fetch commits from top N repos (default: 10)
export COMMIT_PER_REPO=30                 # Commits per repo (default: 30)

# API settings
export API_TIMEOUT=5                      # Request timeout in seconds (default: 5)

# Run with custom settings
COLLABORATOR_MIN_COMMITS=15 python run.py username
```

## How Collaborators Are Detected

The widget finds **meaningful collaborators** by:

1. **Identifying shared repositories**: Looks at repos where the user has committed
2. **Fetching contributors**: Gets all contributors from those repos
3. **Applying thresholds**:
   - Only includes contributors with 10+ commits (configurable)
   - Filters out huge OSS projects (100+ contributors)
   - Focuses on user's top 5 most active repos
4. **Ranking by collaboration**: Sorts by total shared commits across all repos

This ensures collaborators are people you've actually worked with closely, not random contributors from large open-source projects.

## Development

All widgets follow the same pattern:
- Accept data models from `models/`
- Use themes from `themes/`
- Return SVG strings
- Use `utils.card_wrapper()` for consistent styling
