# AutoCliper Frontend

React SPA for managing video clipping jobs with custom style editor.

## Tech Stack

- React 19 + Vite 6
- TailwindCSS 4
- Framer Motion 12
- React Router 7
- Lucide Icons

## Pages

| Page | Path | Description |
|------|------|-------------|
| Dashboard | `/` | Job list, search, status filters |
| New Job | `/new` | URL input, style editor, presets |
| Job Detail | `/jobs/:id` | Clip grid/carousel, progress |
| Clip Viewer | `/jobs/:id/clips/:rank` | Video player, style modal, restyle |
| Settings | `/settings` | General, Render Engine, Users |
| Login | `/login` | Auth |

## Features

- Custom Style Editor (Hook + Subtitle) with live preview
- User presets (save/load/delete per user)
- Preset carousel in NewJob page
- Cache status indicator (shows if URL was processed before)
- Force reprocess toggle with smart description
- Clear Storage function (preserves presets & users)

## Quick Start

```bash
# Install
npm install

# Dev server (port 3000)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Environment

Create `.env` (optional):
```env
VITE_API_URL=http://localhost:8000
```

## Project Structure

```
src/
├── components/
│   ├── StyleEditorModal.tsx   # Full style editor (Presets/Hook/Subtitle tabs)
│   ├── VideoPreviewOverlay.tsx
│   ├── Sidebar.tsx
│   └── ui/                    # Reusable UI components
├── pages/
│   ├── Dashboard.tsx
│   ├── NewJob.tsx
│   ├── JobDetail.tsx
│   ├── ClipViewer.tsx
│   └── Settings.tsx
├── layouts/
│   └── AppLayout.tsx
└── lib/
    ├── api.ts                 # API client with auth
    └── utils.ts               # Helpers
```
