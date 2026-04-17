import { useState } from 'react'

type Props = {
  onSearch: (username: string) => void
}

export function SearchScreen({ onSearch }: Props) {
  const [value, setValue] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = value.trim()
    if (trimmed) onSearch(trimmed)
  }

  return (
    <div className="min-h-screen flex items-center justify-center animate-fade-in-up">
      <div className="text-center w-full max-w-md px-6">
        <h1 className="font-serif text-4xl text-gray-800 tracking-tight mb-2">
          GitHub Stats
        </h1>
        <p className="text-sm text-gray-400 mb-8">
          Generate your profile widget
        </p>
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            value={value}
            onChange={e => setValue(e.target.value)}
            placeholder="Enter GitHub username..."
            autoFocus
            className="flex-1 px-4 py-3 rounded-xl border border-gray-200 bg-white text-sm text-gray-800 placeholder:text-gray-300 focus:outline-none focus:ring-1 focus:ring-gray-300 transition-colors"
          />
          <button
            type="submit"
            disabled={!value.trim()}
            className="px-6 py-3 rounded-xl bg-gray-800 text-white text-sm font-medium hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Go
          </button>
        </form>
      </div>
    </div>
  )
}
