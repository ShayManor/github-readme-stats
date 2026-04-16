"""Theme definitions and color palettes."""

THEMES = {
    # --- Dark themes ---
    "dark": {  # kept for backwards compat; "midnight" is the alias
        "bg": "#121820",
        "card_bg": "#1a2230",
        "card_border": "#2a3444",
        "text": "#d1d9e0",
        "text_secondary": "#7d8895",
        "accent": "#58a6ff",
        "green": "#3fb950",
        "orange": "#d29922",
        "red": "#f85149",
        "purple": "#bc8cff",
        "pink": "#f778ba",
        "grid": "#1e2836",
    },
    "onyx": {  # high-contrast neon on pure black
        "bg": "#09090b",
        "card_bg": "#18181b",
        "card_border": "#27272a",
        "text": "#fafafa",
        "text_secondary": "#a1a1aa",
        "accent": "#a78bfa",
        "green": "#4ade80",
        "orange": "#fb923c",
        "red": "#f87171",
        "purple": "#c084fc",
        "pink": "#f472b6",
        "grid": "#27272a",
    },
    "nord": {  # muted pastel on slate-blue — clearly cooler
        "bg": "#1e2433",
        "card_bg": "#2a3142",
        "card_border": "#3d4659",
        "text": "#e5e9f0",
        "text_secondary": "#8892a4",
        "accent": "#88c0d0",
        "green": "#a3be8c",
        "orange": "#ebcb8b",
        "red": "#bf616a",
        "purple": "#b48ead",
        "pink": "#d08770",
        "grid": "#333d50",
    },
    # --- Light themes ---
    "light": {  # kept for backwards compat; "clean" is the alias
        "bg": "#ffffff",
        "card_bg": "#f6f8fa",
        "card_border": "#d8dee4",
        "text": "#24292f",
        "text_secondary": "#656d76",
        "accent": "#0969da",
        "green": "#1a7f37",
        "orange": "#9a6700",
        "red": "#cf222e",
        "purple": "#8250df",
        "pink": "#bf3989",
        "grid": "#eaeef2",
    },
    "paper": {
        "bg": "#faf8f5",
        "card_bg": "#f5f0eb",
        "card_border": "#e0d8cf",
        "text": "#3d3529",
        "text_secondary": "#7a7062",
        "accent": "#b45309",
        "green": "#4d7c0f",
        "orange": "#a16207",
        "red": "#b91c1c",
        "purple": "#7e22ce",
        "pink": "#be185d",
        "grid": "#ebe5dd",
    },
}

# Aliases so the frontend can use friendly names
THEMES["midnight"] = THEMES["dark"]
THEMES["clean"] = THEMES["light"]

TAG_COLORS = {
    "ml-engineer": "#bc8cff",
    "frontend": "#58a6ff",
    "backend": "#3fb950",
    "fullstack": "#d29922",
    "devops": "#f0883e",
    "database": "#f778ba",
    "mobile": "#ff6b9d",
    "security": "#f85149",
    "data-science": "#79c0ff",
    "systems": "#7ee787",
    "cloud": "#58a6ff",
    "open-source": "#3fb950",
}

GRADE_COLORS = {
    "S": "#ff6b9d",
    "A": "#3fb950",
    "B": "#58a6ff",
    "C": "#d29922",
    "D": "#f0883e",
    "F": "#f85149",
}

FOCUS_COLORS = [
    "#58a6ff",
    "#3fb950",
    "#bc8cff",
    "#d29922",
    "#f0883e",
    "#f778ba",
    "#f85149",
    "#79c0ff",
]

LANG_COLORS = {
    "Python": "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "Go": "#00ADD8",
    "Rust": "#dea584",
    "Java": "#b07219",
    "C++": "#f34b7d",
    "C": "#555555",
    "Ruby": "#701516",
    "Shell": "#89e051",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "Kotlin": "#A97BFF",
    "Swift": "#F05138",
    "Jupyter Notebook": "#DA5B0B",
    "Dockerfile": "#384d54",
}
