# 🏁 Full Course Yellow

Darien Entwistle's motorsport blog + racing news site — races I attend, camping at the track, and the latest headlines.
YouTube: [@djdarien93](https://youtube.com/@djdarien93) · Personal site: [dentwistle.online](https://dentwistle.online)

Live: https://djdarien.github.io/full-course-yellow/

## How it works
- `posts/` — one HTML file per blog post (with a small front-matter header).
- `src/about.html` — About page content.
- `assets/` — CSS and images (photos © Darien Entwistle, reused from dentwistle.online).
- `build.py` — stdlib-only Python builder that renders everything into `_site/`.
- `.github/workflows/pages.yml` — builds and deploys to GitHub Pages on every push to `main`, every 3 hours (to refresh news), or manually.

## Adding a post
1. Create `posts/YYYY-MM-DD-your-slug.html`:
   ```html
   ---
   title: My Race Weekend at Road Atlanta
   date: 2026-10-20
   category: Racing
   excerpt: One or two sentences for cards and previews.
   image: assets/img/your-photo.jpg
   image_alt: Describe the photo
   featured: true
   ---
   <p>Your post body in plain HTML.</p>
   <h3>A section heading</h3>
   ```
   - `image`, `image_alt`, `featured` are optional. Put photos in `assets/img/` (resize to ~1800px wide).
   - The newest post with `featured: true` (or else the newest post) is featured on the home page. Remove `featured: true` from the old one when you feature a new one.
   - `placeholder: true` shows a "Starter" badge — remove it once you've written real content.
   - Embed a YouTube video: `<div class="video"><iframe src="https://www.youtube.com/embed/VIDEO_ID" allowfullscreen></iframe></div>`
2. Preview locally: `python3 build.py && python3 -m http.server -d _site 8000` → http://localhost:8000
3. Commit and push to `main`; the site redeploys automatically.

## Racing news
News is fetched **at build time** in GitHub Actions — no API key is ever in the repo or the browser.
- If the repo secret `NEWSDATA_API_KEY` is set, it uses [NewsData.io](https://newsdata.io) (the same API Volt Report uses) with a motorsport query.
- Otherwise it falls back to the public Motorsport.com RSS feed.

To enable NewsData: **Settings → Secrets and variables → Actions → New repository secret**, name `NEWSDATA_API_KEY`, then re-run the workflow (Actions → "Build & deploy to GitHub Pages" → Run workflow).
