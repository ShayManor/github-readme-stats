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

## Development

All widgets follow the same pattern:
- Accept data models from `models/`
- Use themes from `themes/`
- Return SVG strings
- Use `utils.card_wrapper()` for consistent styling
