# 🏁 Full Course Yellow

Darien Entwistle's motorsport blog + racing news site — races I attend, camping at the track, and the latest headlines.
YouTube: [@djdarien93](https://youtube.com/@djdarien93) · Personal site: [dentwistle.online](https://dentwistle.online)

Live: https://djdarien.github.io/full-course-yellow/

## How it works
- `content/posts/` — one Markdown file per blog post (front matter + HTML/Markdown body). Edited by hand or with Pages CMS.
- `.pages.yml` — Pages CMS configuration (post fields + image folder `assets/img`).
- `src/about.html`, `src/series.html` — About and Series Guide page content.
- `assets/` — CSS and images (photos © Darien Entwistle, reused from dentwistle.online). CMS uploads land in `assets/img/`.
- `build.py` — stdlib-only Python builder that renders everything into `_site/`.
- `.github/workflows/pages.yml` — builds and deploys to GitHub Pages on every push to `main`, every 3 hours (to refresh news), or manually.

## Editing posts in the browser (Pages CMS — free, no secrets)
**One-time setup**
1. Go to **https://app.pagescms.org** and click **Sign in with GitHub** (use the `djdarien` account).
2. When asked, **install/authorize the Pages CMS GitHub App** and give it access to **only** the `full-course-yellow` repository.
3. Open **djdarien/full-course-yellow** (branch `main`) from the Pages CMS dashboard.

**Day to day**
- **New post:** *Blog posts → Add an entry*. Fill in Title, Date, Category, Excerpt, Cover image (upload or pick), optional YouTube URL, and write the body. Click **Save**. Pages CMS commits to `main`; the site rebuilds and is live in about a minute.
- **Edit:** open the post, change it, **Save**.
- **Delete:** open the post → **⋯ / Delete**. It disappears from the blog, home page, and prev/next links on the next build.
- **Images:** upload in the Cover image field or with the image button in the body editor; files go to `assets/img/`. Under the *Media* tab you can manage them.
- **Featured on home page:** tick *Featured*. The newest featured post wins (untick it on the old one if you like).
- **YouTube:** paste a URL in *YouTube video URL*. The video shows at the top of the body, or exactly where you type `{{youtube}}` on its own line.
- **Drafts:** tick *Draft* to keep a post off the site.
- **Starter / Originally published notes:** *Starter* adds the badge; *Starter note* and *Originally published at* add the notes at the top of the post.

## Adding a post by hand
Create `content/posts/YYYY-MM-DD-your-slug.md`:
```markdown
---
title: "My Race Weekend at Road Atlanta"
date: 2026-10-20
category: IMSA
excerpt: "One or two sentences for cards and previews."
image: /assets/img/your-photo.jpg
image_alt: "Describe the photo"
youtube: https://www.youtube.com/watch?v=VIDEO_ID
featured: true
---
<p>Body in HTML…</p>

## …or Markdown
Plain **Markdown** works too (headings, lists, links, images, bold/italic).
```
Only `title`, `date` and `excerpt` are needed. Preview locally: `python3 build.py && python3 -m http.server -d _site 8000` → http://localhost:8000. Commit and push to `main` to publish.

## Racing news
News is fetched **at build time** in GitHub Actions — no API key is ever in the repo or the browser.
- If the repo secret `NEWSDATA_API_KEY` is set, it uses [NewsData.io](https://newsdata.io) (the same API Volt Report uses) with a motorsport query.
- Otherwise it falls back to the public Motorsport.com RSS feed.

To enable NewsData: **Settings → Secrets and variables → Actions → New repository secret**, name `NEWSDATA_API_KEY`, then re-run the workflow (Actions → "Build & deploy to GitHub Pages" → Run workflow).
