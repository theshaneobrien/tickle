# tickle

A self-hosted game portal for indie developers. Think personal itch.io, no accounts, no platform fees, your games on your server.

## What It Does

- **Admin tool** (runs locally or in Docker): Create and manage game entries, upload builds and screenshots, configure metadata
- **Static site generator**: Outputs pure HTML/CSS/JS, deploy anywhere (Nginx, Apache, Caddy, GitHub Pages, S3, literally any web server)
- **Game embedding**: Plays Unity WebGL and Godot HTML5 games directly in the browser via iframes
- **Retro emulation**: Play NES, SNES, Genesis, Game Boy, GBA, N64, PS1, and arcade ROMs in the browser via [EmulatorJS](https://emulatorjs.org). Upload a ROM, pick a system, done. Cores load from CDN on demand, no server-side setup needed
- **3D model viewer**: Showcase 3D prints and models with an interactive Three.js viewer. Supports STL files with orbit controls, lighting, and a multi-model carousel for entries with multiple files
- **itch.io sync**: Import game metadata from any itch.io page, single game or bulk profile import. Pulls title, description, tags, screenshots, cover art, YouTube trailers, and all metadata. No binaries copied, just the catalog data you need to rebuild your portfolio on your own terms
- **Rich social previews**: OG meta tags and Twitter cards for Discord, Twitter, Facebook link embeds
- **Your branding**: Site name, title, tagline, navigation, all configurable. Tickle is the engine; your site is the product
- **Zero dependencies**: Python stdlib server for admin, no NPM, no frameworks, no build tools, no databases, just a server

Demo Video:

[![Watch it in action](https://img.youtube.com/vi/WWZRa3ev110/0.jpg)](https://www.youtube.com/watch?v=WWZRa3ev110)

You can see it here: https://games.jeocities.org

## Quick Start

```bash
git clone https://github.com/theshaneobrien/tickle.git
cd tickle
python3 server.py
```

On first run, visiting `http://localhost:8080` redirects you to the admin panel at `/admin` to set up your site.

### URLs

| URL | Purpose |
|-----|---------|
| `http://localhost:8080/` | Your live site (visitors see this) |
| `http://localhost:8081/admin` | Admin panel (manage games, site settings) |
| `http://localhost:8081/preview/` | Preview with "PREVIEW MODE" banner |
| `http://localhost:8081/api/` | JSON API (used by admin UI) |

### First-Run Flow

1. Open `http://localhost:8080`, this then redirects to `/admin` (no site exists yet)
2. Fill in site name, title, tagline, author, then click **Create Site**
3. Portal is generated automatically, your site is now live at `/`
4. Click **+ New Game** to add your first game
5. Fill in game details, upload a build (zip of Godot/Unity web export or just a zip for a platform)
6. Click **Generate Page** and the game page goes live
7. Repeat for more games

### Docker

```bash
cd docker
docker compose up
```

The `output/` volume persists your site data (games, config) across container restarts. Logs stream to stdout. Use `docker exec -it tickle-tickle-1 bash` to debug inside the container.

## itch.io Import

Already have games on itch.io? Import them in seconds.

From the admin panel, click **Import from itch.io** and paste a URL:

**Single game**: paste a game URL like `https://yourname.itch.io/your-game`. Tickle scrapes the page and pulls in:
- Title, description, long description (formatted HTML)
- Cover image, icon, and all screenshots
- Tags, genre, status, engine, platforms, input methods
- YouTube trailer (if embedded on the page)
- Credits and metadata

You get a full preview to review and edit before confirming. On import, images are downloaded to disk and the game entry is created, ready for you to upload your actual build files.

**Bulk profile import**: paste a profile URL like `https://yourname.itch.io`. Tickle scans the profile, shows every game found, and lets you select which ones to import. Each game is scraped and created sequentially with a progress bar.

This is metadata only. Game binaries are never downloaded. You upload your own builds after import, keeping you in control and preventing unauthorized cloning. Think of it as migrating your catalog, not mirroring your content.

## Adding Games

From the admin panel:

1. Click **+ New Game**, enter a title
2. Fill in metadata (engine, status, description, tags, etc.)
3. Upload a game build: drop a `.zip` of your Godot or Unity web export, upload a ROM for retro games, or point to a custom HTML entry point
4. Engine is auto-detected from build files. For ROMs, select your system from the EmulatorJS dropdown
5. Upload icon, cover image, and screenshots
6. Click **Generate Page** to publish

Games can be **unlisted** via the visibility toggle in the editor. They'll still have a page but won't appear on the portal, so they can still be shared directly.

A red banner appears in the editor when changes haven't been generated yet, so you always know if the live site is out of date.

Games without a WebGL build show the cover image as a full-frame hero instead of an empty viewport. Games with a YouTube trailer show the embedded video instead.

### Retro Games (EmulatorJS)

For retro homebrew, ROM hacks, or demoscene entries:

1. In the game editor, switch the **Web Player Build** mode to **EmulatorJS**
2. Select your target system (Genesis, NES, SNES, Game Boy, GBA, N64, PS1, Arcade, and more)
3. Upload your ROM file (.bin, .nes, .sfc, .gba, .z64, etc.)
4. Generate and you're done. Visitors click Play and the emulator core loads from CDN on demand

No server-side emulation, no WASM blobs to host. The generated page is still pure static HTML.

### 3D Prints

Tickle also supports a **3D Print** content type for showcasing models and physical projects:

1. Set the game type to **3D Print** in the Classification section
2. Upload `.stl` files in the Model Files section
3. The generated page features an interactive Three.js viewer with orbit controls, adjustable lighting, and a thumbnail carousel when you have multiple models
4. Optionally toggle model downloads on/off per entry

## Deploy

The `output/` directory is your complete static site. Upload it however you like:

```bash
# rsync
rsync -avz output/ user@yourserver:/var/www/games.yoursite.org/

# or just copy it
scp -r output/* user@yourserver:/var/www/html/
```

The server also works as a host, run it in Docker and your site is served directly at the container's port. Admin lives at `/admin`. This is useful for a staging area, but some folks also just don't want the hassle of dealing with manual file uploads.

## Project Structure

```
tickle/
├── server.py              # Admin backend + site host (Python stdlib only)
├── admin/index.html       # Admin UI (single file, vanilla JS)
├── templates/             # HTML templates for static generation
│   ├── portal.html        # Index/grid page
│   ├── game.html          # Individual game page
│   └── 3d-print.html      # 3D model viewer page (Three.js)
├── static/shared.css      # Design system
├── docker/                # Docker setup (optional)
│   ├── Dockerfile
│   └── docker-compose.yml
└── output/                # ← Generated site (deploy this, gitignored)
    ├── index.html
    ├── shared.css
    ├── site.json
    ├── games.json
    └── games/
        └── your-game/
            ├── index.html
            ├── screenshots/
            └── ...build files...
```

## Supported Engines and Formats

- **Godot HTML5** - auto-detected from `.pck` + `.wasm` + `.html` files
- **Unity WebGL** - auto-detected from `Build/` directory; CSS is auto-patched for fullscreen iframe embedding
- **EmulatorJS** - NES, SNES, Sega Genesis, Game Boy, Game Boy Color, GBA, Nintendo 64, PlayStation, Arcade (FBNeo), Master System, Game Gear, Sega CD. Cores load from CDN, nothing to install
- **3D Print / STL** - interactive Three.js viewer with orbit controls, wireframe toggle, and multi-model carousel
- **Custom / Manual** - point to any HTML file as the entry point for Phaser, Pixi.js, PlayCanvas, or any other browser-based engine

Upload your web export as a `.zip` file and Tickle extracts it, detects the engine, and sets the game file entry point automatically. For ROMs, select a system and upload the file directly. For custom engines, switch to Manual mode and specify the entry point HTML.

## Philosophy

Web 1.0ish simplicity. You edit locally, you upload files, your site is static HTML. No CDNs, no bundlers, no CI/CD required (though you can add them). The admin tool is just a fancy form that writes files to disk.

## AI Disclosure

This project was created with the help of Claude Code and Open Code with locally run models. All code has been reviewed but there may still be mistakes.

AI did not come up with this app idea, it has been entirely tailored to my use cases for a locally hosted itch.io clone. The themes, look, design and functionality are all things I spent writing out a design for, writing prototypes, testing the flow and then working with the AI tools to flesh them out.

I am a recent father of an almost two month old, I have been coding and devloping games and apps for well over a decade now and I just wanted to make something cool with the extremely limited time I have.

I spent more hours than a newborn really should allow, hours testing it on my own devices, over and over, refining the development process, reviewing every line, coming up with a QA process and working with the tools to fix them.

This is not "make me an itch.io clone", this is something I thought should exist and utilized AI as a tool to help bring it to fruition, both as a method to accelerate development and for my own learning and curiosity about how these tools could be used going forward.

The use of AI may mean you will just ignore this tool, and that's fine, but if not, I hope you enjoy it, and if you are so inclined, help to improve it.

## License

[CC BY-NC-SA](https://creativecommons.org/licenses/by-nc-sa/4.0/)
