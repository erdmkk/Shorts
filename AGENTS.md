# AGENTS.md — Puzzly Shorts Generator

## Mission

Build a completely local, deterministic, one-click generator for polished, language-free Puzzly for Kids YouTube Shorts. It must run on Windows with CPU rendering and must not require paid APIs, cloud rendering, copyrighted assets, narration, subtitles, or manual video editing.

The current feature pass adds a persistent Manual Placement editor to standalone Hidden Motion Hunt while preserving all approved games, publishing, and rendering architecture. Line Follow remains disabled.

## Product workflow

1. Run `setup.bat` once.
2. Run `run.bat` to open the Streamlit UI.
3. Choose puzzle type, relevant theme/operation, difficulty, challenges per video, video count, quality, and optional seed.
4. Generate one or a batch of videos.
5. Preview results and find matching MP4/JPG files plus disposable metadata manifests in `output/`.

Everything required for normal generation must remain local and near-zero-cost.

`output/` is disposable: users may delete generated files without resetting duplicate prevention or numbering. The authoritative history is the local SQLite database at `data/generation_history.sqlite`; deleting that database intentionally resets duplicate memory and sequence history.

## Technology and export

- Python 3.11+, Streamlit, MoviePy 2.x, Pillow, NumPy, imageio-ffmpeg, dataclasses, pytest.
- Final: render visuals internally at 2160×3840 and 30 visual FPS, downsample every frame with LANCZOS to 1080×1920, then export at 30 FPS with H.264/libx264, CRF 17, medium preset, yuv420p, AAC 48 kHz, and fast-start MP4.
- Draft: render visuals internally at 540×960 and 15 visual FPS, export at 540×960 and 30 FPS with CRF 28 and the ultrafast preset. Content and timing remain identical to Final.
- Keep these profiles centralized in `puzzly/config.py`; do not scatter quality constants through rendering code.
- Duration is dynamically calculated from intro, round count/type, and outro. Never assume 15 seconds.
- Preserve aspect ratios and support CPU-only rendering.

## Active product

The active puzzle list is a current implementation inventory, not a permanent whitelist or a fixed product boundary. A direct user request may add a new puzzle type. When the newest direct user instruction explicitly requests a new game, it takes precedence over older puzzle-count or product-inventory statements in this file; no separate permission is required to update the inventory, UI, Mixed pool, tests, metadata, or related registrations needed for that game.

Current active inventory: Quick Math, Missing Number, Puzzle Fit, Find the Exit, Memory Challenge, Flash Count, Lucky Pick, Hidden Motion Hunt, and the newly requested Cube Count.

Protect existing puzzle games from unrelated changes. Adding or changing one requested game does not authorize redesigning or altering the gameplay of other games unless the user explicitly asks for those changes.

Line Follow is disabled/experimental unless a direct user instruction explicitly re-enables it. Until then, keep its source, tests, rendering compatibility, old manifests, and SQLite records, but do not expose it in the Streamlit selector, mixed pool, or normal batch generation.

Odd One Out and Counting are deprecated. Their old files may remain if harmless, but they must not be reachable from the UI, mixed generation, metadata, documentation, defaults, or new samples.

Mixed batch generation selects among active types that need no upload. Hidden Motion Hunt is standalone-only because it requires a user background. Cube Count is a standard active type and may participate in Mixed mode.

## Product-scope instruction precedence

- The newest direct user instruction takes precedence when it conflicts with an older puzzle inventory, fixed game count, version label, or feature-scope statement in this file.
- An explicit request to implement a new puzzle type is sufficient authorization to add it and update the active inventory; do not pause for separate permission solely because the game is absent from an older list.
- Treat inventory and version-specific sections as descriptions of the current implementation, not permanent prohibitions on future explicitly requested work.
- This precedence applies to product scope. Continue to preserve project-wide architecture and safety rules unless the user explicitly requests a compatible architectural change.
- In particular, preserve SQLite generation history, duplicate prevention, filename conventions, disposable output-folder behavior, Draft/Final rendering profiles, the safe audio pipeline, direct cover generation, deterministic validation, and local/offline-first operation.
- Continue protecting unrelated existing games from incidental gameplay or visual changes.
- Line Follow remains disabled/experimental unless explicitly re-enabled.

## Multi-round architecture and pacing

`VideoSpec` contains validated `rounds`, `intro_duration`, `outro_duration`, `round_duration`, and computed `total_duration`.

Auto defaults: Quick Math, Missing Number, and Puzzle Fit use 5 rounds. Quick Math and Missing Number use 4.0 seconds thinking; Puzzle Fit uses 4.0 seconds for Easy/Medium and 5.0 seconds for Hard. Find the Exit uses 4 rounds with Easy 5.0, Medium 6.0, Hard 7.0 seconds thinking. Flash Count uses 4 rounds by default and supports manual 3/4/5. Memory Challenge and Lucky Pick each use one fixed game. Hidden Motion Hunt uses one continuous 18-second scene. Centralize timing and compute duration dynamically. Same seed/settings reproduce the content. Prevent duplicates.

## Shared visual timeline

- Intro: 1.0–1.5 seconds, concept-specific, energetic, and branded. Show an English EASY, MEDIUM, or HARD badge. Quick Math uses +, −, ×, ÷; Missing Number uses a short sequence with a missing slot; Puzzle Fit uses a coherent board/hole/options cue with puzzle-piece imagery and no unrelated X or primary question-mark cue.
- A small decorative dot indicator near the top shows round progress without words.
- Thinking uses a thin rounded progress bar that shrinks smoothly; never use a 5–4–3–2–1 countdown.
- Between rounds use a restrained 0.3–0.5 second scale/fade, card slide, or soft wipe.
- Outro: 0.7–1.0 seconds with brand mark, small bounce, and subtle sparkle; visually loop-compatible.
- No voice, spoken language, subtitles, written instructions, welcome, subscribe text, or negative failure cues.

## Quick Math V7

- Intro and direct JPG cover are concept-only: show `QUICK MATH`, the four operator icons (+, −, ×, ÷), and the difficulty badge, but never a generated equation or an extra decorative question mark.
- Default 5 rounds, 5.7 seconds per round: 0.35-second entrance, 4.0-second thinking, 0.7-second reveal, and 0.65-second success/transition.
- Operations: Addition, Subtraction, Multiplication, Mixed. V7 does not generate division.
- Every equation contains exactly one unknown. Addition supports result/left/right unknowns at all levels. Easy subtraction uses result unknowns only; Medium/Hard subtraction and multiplication support all three positions.
- Easy uses small addition and simple non-negative subtraction with no multiplication. Medium adds non-trivial 2–5 table multiplication; Hard uses larger readable values and multiplication. Use `×`, never lowercase `x`.
- Answers are unique integers with no negative result, fractions, multiplication by 0/1, duplicate equations, or one-template-only multi-template videos where avoidable.

## Missing Number V7

- Default 5 rounds with the shared 4.0-second thinking window.
- Use large rounded number cards/capsules with sufficient padding for two-digit values; never use cramped circles. The sequence is the dominant focus inside a centered rounded puzzle card. Calculate complete group bounds and center at x=540 within approximately ±20 px.
- Each sequence has exactly one obvious family: constant addition, constant subtraction, or integer multiplication. Never use alternating/mixed rules.
- Easy is 80% small addition with occasional simple subtraction. Medium balances addition/subtraction and includes controlled ×2. Hard combines larger arithmetic steps with ×2, ×3, ×4, and ×5 geometric sequences.
- Keep every value from 0 through 999, vary internal missing positions, and avoid duplicate sequences and repeated family/rule pairs inside a video.
- Exactly one internal slot is hidden and every answer/pattern is validated.
- Reveal the answer in place with the shared progress timer and success treatment.

## Puzzle Fit V7

- Intro and direct JPG cover use a fixed stylized 2×2 board, dashed missing slot, loose sample piece, title, and difficulty badge. They never reuse or disclose a generated playable board.
- Default 5 rounds. Easy/Medium retain 4.0 seconds and three candidates. Hard uses exactly 5.0 seconds and four candidates in a centered, non-overlapping 2×2 layout. Actual rounds begin with one empty hole and all loose candidates already visible; never show the answer leaving the board.
- Generate local rounded jigsaw tabs and sockets on 2×2, 2×3, and 3×3 boards, with corner, edge, and interior holes.
- Hole and correct candidate use identical geometry. Validate every shared seam, outer edge, candidate, missing slot, and answer.
- Use an empty contrasting hole with a differentiated dashed outline, without a question mark.
- Keep all candidates plausible, with exactly one geometric match, subtle shadows, comfortable spacing, and no A/B/C labels.
- Show no correct-answer cue during thinking. Reveal by highlighting, lifting, moving, and precisely snapping the correct piece into the hole, followed by a solved hold.
- Intro demonstrates a hole, loose pieces, and a snap only; no piece-removal tracking.

## Find the Exit — Route Quality Polish

- Auto 4 rounds; Easy/Medium/Hard thinking times 5/6/7 seconds.
- One clear start and three natural symbol-marked boundary exits. Exactly one exit is reachable.
- Generate sparse readable 5×5, 6×6, or 7×7 maze graphs. Three disjoint rooted trees guarantee a unique reachable exit; independently validate connectivity, acyclicity, and the reveal route. Every visible top exit must connect inward immediately, including both false exits, so none is visibly sealed at its icon.
- Build the correct route first with a deterministic loop-erased walk, then grow the three disjoint trees around it. Easy requires at least 3 turns and 1 route branch; Medium at least 5 turns, 1 downward revisit, and 3 route branches; Hard at least 8 turns, 2 downward revisits, and 5 route branches. Difficulty must be visibly meaningful without reducing phone readability.
- Reveal the route progressively from start to exit, then a small positive success indication. Never show answer cards.
- Intro demonstrates a simple start, exits, and route trace with a difficulty badge.

## Line Follow V8.1

- Auto 4 rounds; Easy/Medium/Hard thinking times 5/6/7 seconds.
- Easy uses 3 paths and 2 controlled crossings; Medium uses 4 paths and 6 crossings; Hard uses 5 paths and 12 crossings. Every path has one top anchor, one unique destination, and meaningful interaction with the route group.
- Build routes as C1-continuous floating-point cubic Bézier segments with shared vertical tangents at stage boundaries. Adaptively subdivide by curvature and a 5-pixel maximum chord; quantize only at the final high-resolution raster boundary.
- Rasterize only the Line Follow path crop at 4× Final resolution. Draw one continuous joint-smoothed centerline with round end caps only, then downsample with LANCZOS into the existing 2× Final composition. Never stamp a circle at every sampled vertex.
- Every crossing is a deliberate bridge: a short clean surface halo clears only the underpass, then a substantially longer top centerline reconnects to untouched base stroke on both sides. Foreground and halo must never share endpoints; the top path must have no centerline or bridge-end gap.
- Hard requires at least 8 target crossings, three lane spans, three direction changes, three interactions for every visible path, and interaction with at least three distinct decoys. It also requires at least four target interactions below mid-height, two in the final third, two in every vertical third, no target idle run longer than two stages, and at least one lower-half interaction for all five paths. All exits remain structurally plausible late into the puzzle.
- All lines use the same neutral appearance during thinking. Only the designated source is highlighted.
- Validate the source, permutation of destinations, every overpass, bounds, deterministic routing, and correct answer.
- Reveal by tracing the designated line and marking its destination. The intro demonstrates this without instructions.

## Memory Challenge V6.1

- Generate exactly five procedural tokens on one board. A token is a unique geometric shape plus one curated color; active shapes are circle, triangle, square, star, hexagon, heart, diamond, and pentagon. Never repeat a shape and do not combine pentagon with hexagon on the same board.
- Use the fixed centered 3+2 layout. All tokens pop in synchronously, remain static for exactly 3.0 seconds of memorization, then receive numbered covers in the identical positions.
- Randomize four token positions into a deterministic question order. Each question presents a large target token and readable question mark, runs exactly 3.0 seconds of progress-bar thinking, then immediately highlights/flips the correct tile. Previously revealed positions stay open.
- The fifth position is excluded from timed questions. After question four, wait 0.4 seconds, flip it automatically, and hold the complete board for 1.25 seconds before the outro.
- Difficulty changes only curated OKLab color similarity. Easy requires minimum pair distance 0.125 and average 0.235; Medium requires minimum 0.075 and average 0.19; Hard requires minimum 0.032, average 0.068–0.16. Every color must also maintain at least 0.10 OKLab lightness separation from all Puzzly backgrounds.
- Normalize every silhouette into a shared safe area and apply small per-shape optical scale/vertical offsets. Center the visible shape, outline, gloss, and restrained lower shadow by eye; never let token alpha touch its raster or white-card edges.
- The 1.5-second intro is intentionally simple: one large question mark, a centered 2×2 group of four colorful tokens on white cards, and the difficulty badge. It uses no numbered demo cards, answer reveal, or tutorial sequence and does not reuse the real board.
- The old 24-object PNG library may remain on disk for compatibility but is deprecated and is not imported or loaded by active Memory generation/rendering.
- Store five shapes, color IDs/values, positions, four-position question order, and final automatic position in the validated spec and manifest. These fields drive fingerprinting/history.
- Use no written instruction, object names, voice, subtitles, negative cue, or touch-game treatment.

## Flash Count V9

- Intro and matching direct JPG cover use the short global cue `How many?` above the existing six-token concept composition; never add a redundant standalone question mark or show an answer.
- Use one deterministic shape and one deterministic base color for the entire video. Supported shapes are circle, triangle, square, star, hexagon, heart, diamond, and pentagon. Counts and positions change between rounds.
- Default to four rounds; manual 3/4/5 remains supported. Every difficulty uses the same unbiased 5–10 shape pool. Never repeat a count in consecutive rounds, but allow non-consecutive reuse so round history does not create elimination clues.
- Place identical, unrotated, uniformly sized tokens with deterministic random-sequential/Poisson-disc-like scatter. Enforce safe bounds, bounding-box separation, minimum center distance, broad coverage, quadrant balance, and limits on row/column alignment. Never use a visible grid. Token size may respond to count/readability only, never difficulty.
- Pop every shape in synchronously for 0.2 seconds, then keep the complete field fully visible for exactly 1.20 seconds on Easy, 0.90 seconds on Medium, or 0.65 seconds on Hard. The fully-visible timer starts after pop-in. Hide the entire field behind one opaque rounded panel, not per-token covers. Show only a large question mark and a subtle progress bar during exactly 3.0 seconds of thinking.
- Reveal the same shapes in the same positions, then show the exact count centered underneath for a 1.0-second solved hold. Validate answer/count identity and every layout before rendering.
- The 1.5-second standardized intro and direct 1080×1920 JPG cover use exactly six tokens in one curated scatter template, `How many?`, and the difficulty badge. Intro/cover shape and color must match the generated video's identity. Covers contain no answer, standalone question mark, or progress bar.
- Persist shape ID, color ID, round counts, ordered positions, duration, filenames, and cover filename in fingerprints/history/manifests. Use the V7 safe audio pipeline.

## Lucky Pick — Entry Corridor Redesign

- One no-difficulty game per video. Select one deterministic shape—circle, square, triangle, star, diamond, hexagon, heart, or pentagon—and use it for all seven differently colored targets. Hold selection unchanged for exactly 5.0 seconds.
- Choose among six curated board templates plus deterministic optional mirroring. Each board is one connected, loop-free corridor tree with a single bottom-center entrance and exactly seven terminal endpoints. The shared trunk branches naturally upward and sideways using horizontal/vertical segments and exact 90-degree turns only; targets are centered exactly on terminal endpoints.
- During the unchanged 5.0-second selection, show only `Pick One`, the corridor board, seven targets, and progress. Never show a redundant standalone question mark, the character, or a central character box. After selection, the character enters visibly from the bottom entrance, then follows the tree's shared branches between terminals without diagonal corner cutting.
- Use one constant 640 logical-pixel/second speed for every route and elimination, without endpoint easing, late-game speed multipliers, or extra hesitations. Keep the 0.58-second eat sequence visually distinct from travel.
- Use explicit idle, selection, travel, eat-anticipation, eat, post-eat, and winner states. The simplified turquoise character is a 196-pixel round side-profile blob with one restrained eye, no feet or tail, and a small closed mouth contained inside its silhouette. It never opens or closes its mouth. Targets are 136 logical pixels and corridors are 170 pixels wide; the visible body is about 149 pixels wide, so the character clearly dominates targets while fitting the route. Never use Pac-Man visual language.
- Elimination uses target-only feedback: brief pop, fast shrink/removal, four restrained particles, and no mouth animation. Keep the 0.58-second eat-state timing for audio/timeline compatibility.
- The six curated templates use asymmetric meandering spines with staggered branches instead of a symmetric castle-like footprint. Reduce meaningless interior holes while retaining one connected loop-free tree, exact orthogonal geometry, and target centers anchored to terminal endpoints.
- The winner is never eaten and receives scale, halo, sparkles, ding, and a 1.7-second hold. Dynamic route timing keeps normal videos around 20.5–24 seconds.
- The 1.25-second intro and direct JPG cover show the video's clean corridor board, seven actual terminal targets, and a clear `Pick One` prompt without an additional question mark. Show no character, winner clue, progress bar, or difficulty badge.
- Fingerprints/manifests store template ID, mirror state, shape ID, color-terminal mapping, winner, elimination order, and dynamic timeline. Keep `PZ_XXXX_lucky_pick` filenames and blank/N/A difficulty.

## Hidden Motion Hunt V1

- Standalone-only active puzzle type; exclude it from Mixed mode because a JPG/JPEG/PNG background upload is required.
- Preserve source aspect ratio and center-crop/cover it to Draft or Final 9:16 dimensions without stretching. Cache a decoded local PNG by SHA-256 source-content hash.
- Offer Manual Placement first and Auto Placement second. Auto keeps exactly seven objects with two Easy-size (50–60 px), two Medium-size (34–44 px), and three Hard-size (20–28 px). No difficulty control is exposed.
- Manual Placement supports 1–20 circle, square, triangle, star, diamond, hexagon, or pentagon objects. Store shape, color, `x_pct`, `y_pct`, Final-pixel size (8–120), Final-pixel jump height (2–40), object ID, and phase offset.
- Show a live 9:16 background preview with a visible selected-object marker, layer selector, numeric X/Y sliders, size/jump sliders, shape/color controls, and Add/Delete/Save/Clear actions. Persist valid layouts as local JSON keyed by background hash and restore them when the same image is uploaded later.
- Keep all object motion envelopes inside safe bounds with no overlaps and at least 44 logical pixels of extra spacing. Manual generation must preserve saved positions, sizes, jump heights, shapes, and colors exactly.
- Use only deterministic vertical sine bounce with a fixed four cycles across exactly 18.0 seconds. X and scale remain constant; seeded phase shift provides batch variation while preserving the saved layout and a mathematically matching loop boundary.
- Use no intro, countdown, reveal, answer screen, or outro. Keep the scene continuous and use a silent stereo compatibility stream with no puzzle SFX.
- Fingerprint and manifest include placement mode, source background hash, seed, coordinates, shapes, colors, sizes, jump heights, cycle/phase values, and duration. Keep `PZ_XXXX_hidden_motion_hunt` filenames with blank/N/A difficulty.

## Puzzly Visual System V4

- Clean modern children’s mobile-game UI: polished 2D, rounded geometry, bold friendly outlines, subtle depth/shadows/highlights, pastel-bright semantic colors, and strong contrast.
- Central palette roles: `background`, `surface`, `primary`, `secondary`, `accent`, `success`, `outline`, `text_dark`, `text_light`. Do not scatter uncontrolled colors.
- Background variants use soft gradients, large low-contrast blobs, tiny dots/stars/puzzle motifs near edges, with a clean center. Do not use the old large white corner circles.
- Supersample important vector artwork at 2×–4× and downsample with LANCZOS when practical.
- All important rounded cards, option tiles, badges, intro panels, branding surfaces, and progress bars use the centralized V6 rounded-surface helper. Rasterize its fill, inset border, radius, opacity, and scaled shadow directly in a localized 2× mask on the active canvas, then downsample that patch once with LANCZOS. This gives critical Final corners effective 4× coverage while retaining the approved 2× global pipeline.
- Scale radius, stroke, blur, and shadow offset together; clamp radius inside the surface bounds. Do not enlarge low-resolution masks or blur borders to conceal aliasing. Reduce radius only if a specific surface remains visibly broken after high-resolution rasterization.
- Use local Segoe UI/Arial bold or semibold with DejaVu Sans fallback; never require font downloads.
- Main composition target center is x=540. Calculate complete bounds; do not intentionally shift content left for Shorts controls.
- Important content may occupy roughly x=100..980. Repeated items and option cards require explicit comfortable gaps and collision checks. If needed, scale the whole group proportionally.
- Provide reusable bounds, centering, uniform-gap, easing, card, shadow, progress, transition, and layout helpers.
- Difficulty backgrounds are centralized: Easy `#E7F8EF`→`#D8F1E4` mint, Medium `#E8F3FF`→`#D9EAFB` sky, and Hard `#F9EAF2`→`#F0DDEC` lavender-pink. Use light decorative accents, preserve white-card contrast, and retain visible text badges so color is never the only cue.

## Audio V7

Generate royalty-free effects locally: intro pop, object pop, soft timer pulse, answer ding, puzzle snap, sparkle, transition whoosh. Keep them soft and toy/game-like. No harsh buzzers or voices. Use float64 internally at 48 kHz, remove meaningful DC, apply an 8 ms smooth squared-sine fade at both SFX boundaries, keep individual peaks below −7 dBFS, and transparently scale overlapping mixes to at most −1 dBFS before integer PCM conversion. Never rely on hard clipping.

## UI and metadata

Streamlit fields: Puzzle Type (including Memory Challenge, Flash Count, Lucky Pick, Hidden Motion Hunt, and Cube Count; excluding experimental Line Follow), Theme when relevant, Difficulty, Operation, Challenges per video, Number of videos, Quality, Optional Seed. Lucky Pick has no difficulty or challenge control. Hidden Motion Hunt has no difficulty/challenge control and instead shows its required upload, Manual/Auto selector, and Manual editor. Show dynamic duration, progress, elapsed time, output path, previews, and Windows output-folder button.

Metadata examples: `Can You Solve All 5? ➕🧠 #shorts`, `Can You Find All 5 Missing Numbers? 🔢 #shorts`, and `Which Piece Fits? 🧩 #shorts`. Descriptions remain short and child-friendly. Never use IQ/genius/deceptive failure claims. Manifests include sequence, matching cover filename, round count, and dynamic duration. Metadata CSV files are reports only and are never authoritative history.

## Publishing history, filenames, and covers

- Use Python `sqlite3` and `data/generation_history.sqlite`; no server or cloud database.
- The database is authoritative for fingerprint uniqueness and the global monotonically increasing sequence. Never derive a new sequence by scanning `output/`.
- Commit a fingerprint and sequence only after both video and cover render successfully. Database assignment is transactional; failures do not consume a fingerprint or sequence.
- New basenames use `PZ_{sequence:04d}_{puzzle_type_slug}_{difficulty_slug}`, for example `PZ_0024_memory_challenge_hard`. Keep lowercase ASCII-safe slugs and do not rename legacy files.
- Write a matching MP4 and JPG to the same output directory. Covers are rendered directly from a deterministic, clean puzzle hero state at Final 1080×1920 resolution, saved as JPEG quality 94, and are not decoded screenshots of MP4 files.
- Back up legacy `data/history.json` before one-time migration and retain it after verification.

## Validation and tests

Never render an invalid educational puzzle. Validate every video and round before export.

- Quick Math: at least 300 Easy, 400 Medium, and 500 Hard specs covering valid operations/templates, one unknown, integer answers, difficulty limits, template variety, and determinism.
- Missing Number: at least 300 Easy, 400 Medium, and 500 Hard specs covering family distributions, valid answers/rules, readable value bounds, no within-video duplicates, and determinism.
- Puzzle Fit: at least 1,000 rounds covering coherent boards, Easy/Medium three-candidate stability, Hard four-candidate layout and 5-second thinking, exactly one match, determinism, bounds, and no overlap.
- Multi-round: Auto defaults, explicit 3/4/5, computed durations, manifest round count, and unique video fingerprints.
- Layout: frame containment, visual center offset (normally ≤20 px), non-overlap, no clipped text/candidates, and separation of round indicator from content.
- Memory Challenge: generate at least 500 Easy, 500 Medium, and 700 Hard specs. Validate one board, five unique shapes/colors/positions, four unique timed questions, excluded final token, determinism, duration, fingerprints, background contrast, and statistically ordered OKLab separation. Validate shape bounds and the full reveal-state progression.
- Flash Count: generate at least 300 Easy, 400 Medium, and 500 Hard specs. Validate the unbiased shared 5–10 count pool, difficulty-specific visible times, no consecutive duplicate counts, allowed non-consecutive reuse, one shape/color per video, exact answers, safe non-overlapping scatter, coverage/alignment quality, determinism, fingerprints, intro/cover identity, and Line Follow deactivation.
- Find the Exit: validate immediate inward passages for all three exits, exact one-exit reachability, tree acyclicity, route correctness, deterministic generation, route length/turn/horizontal/downward movement thresholds, route branch competition, and increasing Easy/Medium/Hard complexity.
- Hidden Motion Hunt: validate required decodable upload, layout save/load, deterministic background hash/spec/fingerprint, Auto 7-object 2/2/3 tiers, Manual 1–20 objects and exact saved properties, supported shapes/colors, size/jump ranges, vertical-only motion, safe bounds, non-overlap/spacing, periodic loop state, exact 18-second duration, standalone Mixed exclusion, blank difficulty, filename, history, and manifest fields.
- Lucky Pick: generate at least 700 specs. Validate one shared supported shape, seven distinct colors, all six curated asymmetric templates and mirrors, one bottom entrance, seven safe terminal endpoints, one connected loop-free orthogonal corridor tree, exact 90-degree turns, terminal anchoring, path continuity between eliminations, unified-mask corridor rendering, constant 640-pixel/second travel, character/target/corridor scale balance, hidden character during selection, no mouth animation, target pop/shrink removal, exact 5.0-second selection, `Pick One` intro/cover, dynamic timing, deterministic winner/order/fingerprint, uniform winner distribution, winner survival, manifests, filenames, and UI hiding.
- Rounded surfaces: verify supersampling-aware radius/stroke scaling, bounds, unclipped corners, LANCZOS downsampling, and intermediate antialiased edge colors without brittle screenshot equality.
- Preserve relevant infrastructure tests; remove obsolete active-product expectations for Odd One Out and Counting.

## Required acceptance outputs

For the Hidden Motion Hunt implementation pass, run only lightweight code-level tests. Do not render Draft/Final videos, covers, contact sheets, or quality frames; the user performs visual acceptance later.

## Windows, logging, branding, and reliability

- `setup.bat` creates/activates `.venv`, installs pinned dependencies, runs an environment check, and reports success/failure.
- `run.bat` activates `.venv` and opens Streamlit.
- Use `pathlib`; no user-specific absolute paths, server databases, secrets, Docker, authentication, or network dependency during generation. Standard-library SQLite is the sole persistent store.
- Log startup, seeds, puzzle type, validation, render lifecycle, output, duration, and exceptions to `logs/puzzly.log`.
- Use `assets/branding/logo.png` automatically when present; otherwise use the isolated generic puzzle-piece mark.
- Cache/reuse static work and audio, avoid huge PNG sequences, clean temporary files, preserve old generated filenames, and never overwrite existing outputs.

## Development order

1. Add persistent Manual layout schema and restore-by-background-hash storage.
2. Add live preview, layer/property controls, and Add/Delete/Save/Clear UI.
3. Route Manual and Auto configs into vertical-only looped rendering and manifests/fingerprints.
4. Run focused lightweight tests, update this file, and stop without rendering media.

## Out of scope

Do not add puzzle types that the user did not request. Explicitly requested new puzzle types are in scope and must be integrated using the preserved project architecture. Automatic YouTube upload, analytics, cloud services, and paid/generated-asset APIs remain out of scope unless a newer direct instruction explicitly and compatibly changes that scope.

## Completion report

Report Hidden Motion Hunt behavior, files changed, internal sizes/counts, motion and crop model, upload/UI behavior, SQLite/fingerprint integration, lightweight tests, limitations, Line Follow status, and confirmation that no samples or manual visual checks were performed.
