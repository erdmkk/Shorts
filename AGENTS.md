# AGENTS.md — Puzzly Shorts Generator

## Mission

Build a completely local, deterministic, one-click generator for polished, language-free "Puzzly for You" YouTube Shorts for an adult audience. Videos should make adult viewers instantly think "challenge accepted": sleek, high-contrast, brain-teaser styling, a strong first-second hook, real tension, and a satisfying payoff. This is not a children's channel. It must run on Windows with CPU rendering and must not require paid APIs, cloud rendering, copyrighted assets, narration, subtitles, or manual video editing.

The current feature pass adds a persistent Manual Placement editor to standalone Hidden Motion Hunt while preserving all approved games, publishing, and rendering architecture. Line Follow is back, rebuilt as Weave V8 and produced only in Hard (see its section). Flash Count is now the number flash game (see its section).

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

Current active inventory: Quick Math, Missing Number, Find the Exit, Flash Count, Lucky Pick, Hidden Motion Hunt, Cube Count, Bounce Arena, Line Follow, Chess: Mate in 1, Matchstick Math, Cup Shuffle, Mind Mix, and Laser Maze. **Paused at the user's request** (off the selector, the Mixed pool, and batch production, because they lost views on their own; they still exist, play inside Mind Mix and the Brain Test, and render from old records): Puzzle Fit, Memory Challenge, and Shade Spot (`registry.PAUSED_PUZZLE_TYPES`; `generate_spec` still makes them, `generate_unique_specs` refuses them). (Removed at the user's request, do not re-add or re-suggest: a Cube Net game, "which cube does this net fold into?".)

Audience data so far: the brain games (Find the Exit, Quick Math, Puzzle Fit) get the most views and engagement, far more than chance games. New games should make viewers think hard, not rely on luck.

Protect existing puzzle games from unrelated changes. Adding or changing one requested game does not authorize redesigning or altering the gameplay of other games unless the user explicitly asks for those changes.

Line Follow was removed once after several redesigns ("it never turned out the way I wanted"), then the user asked for it to be fixed and brought back: it is active again (selector and Mixed pool) as Weave V8, produced only in Hard. Only the user decides whether it stays.

Odd One Out and Counting are deprecated. Their old files may remain if harmless, but they must not be reachable from the UI, mixed generation, metadata, documentation, defaults, or new samples.

Mixed batch generation selects its explicitly registered safe pool rather than every active type. Hidden Motion Hunt is standalone-only because it requires a user background. Bounce Arena is standalone-only in V1. Chess: Mate in 1 is standalone-only (a fixed 30-second still). Matchstick Math and Cup Shuffle are standalone for now (always 3 levels). Cube Count is a standard active type and may participate in Mixed mode. Mind Mix is standalone (it is already a mix). Laser Maze is standalone for now.

## Product-scope instruction precedence

- The newest direct user instruction takes precedence when it conflicts with an older puzzle inventory, fixed game count, version label, or feature-scope statement in this file.
- An explicit request to implement a new puzzle type is sufficient authorization to add it and update the active inventory; do not pause for separate permission solely because the game is absent from an older list.
- Treat inventory and version-specific sections as descriptions of the current implementation, not permanent prohibitions on future explicitly requested work.
- This precedence applies to product scope. Continue to preserve project-wide architecture and safety rules unless the user explicitly requests a compatible architectural change.
- In particular, preserve SQLite generation history, duplicate prevention, filename conventions, disposable output-folder behavior, Draft/Final rendering profiles, the safe audio pipeline, direct cover generation, deterministic validation, and local/offline-first operation.
- Continue protecting unrelated existing games from incidental gameplay or visual changes.
- Line Follow is active (Weave V8, Hard only).

## Multi-round architecture and pacing

`VideoSpec` contains validated `rounds`, `intro_duration`, `outro_duration`, `round_duration`, and computed `total_duration`.

Auto defaults: Quick Math uses 4 levels (see its section). Missing Number uses 5 rounds; Puzzle Fit (V11) always uses 3 levels. Missing Number uses 4.0 seconds thinking; Puzzle Fit uses 5.0 seconds for every difficulty (see its section for its own intro/outro timing). Find the Exit uses 4 rounds with Easy 5.0 and Medium 6.0 seconds thinking; Hard thinks 5, 6, 7, 8 (and 9) seconds on levels 1–4 (5). Flash Count uses 4 levels by default and supports manual 3/4/5. Memory Challenge always has 3 levels (see its section) and Lucky Pick uses one fixed game. Hidden Motion Hunt uses one continuous 18-second scene. Centralize timing and compute duration dynamically. Same seed/settings reproduce the content. Prevent duplicates.

## Shared visual timeline

- Intro: 1.0–1.5 seconds, concept-specific, energetic, and branded. Never show an EASY, MEDIUM, or HARD difficulty badge in intros or covers. Quick Math uses +, −, ×, ÷; Missing Number uses a short sequence with a missing slot; Puzzle Fit uses a coherent board/hole/options cue with puzzle-piece imagery and no unrelated X or primary question-mark cue.
- A small decorative dot indicator near the top shows round progress without words.
- Thinking uses a thin rounded progress bar that shrinks smoothly; never use a 5–4–3–2–1 countdown.
- Between rounds use a restrained 0.3–0.5 second scale/fade, card slide, or soft wipe.
- Outro: 0.7–1.0 seconds with brand mark, small bounce, and subtle sparkle; visually loop-compatible.
- Every game ends with the shared `draw_cta` "Follow for more" call to action: a solid rounded pill button with a clean Segoe UI Bold label (never the handwritten display font).
- No voice, spoken language, subtitles, written instructions, welcome, subscribe text, or negative failure cues.

## Per-video background tone (all dark-theme games)

Each Puzzly for You video uses one dark background tone from `DARK_THEMES` in `puzzly/config.py` (`THEME_CHOICES`): the classic dark tones violet, ocean, teal, gold, emerald, ember, and plum, and the **vivid tones** lemon (`Canlı sarı`, a bright light yellow), tangerine, pink, cyan, and lime. Crimson is retired from the UI and the random pool but stays in `DARK_THEMES` so older records still render.
- Vivid tones (the user's request: the published videos looked mostly dark, so add liveliness while keeping the dark theme): the edges and corners stay as dark and vignetted as ever and only the colour toward the middle is bright and saturated. `THEME_GLOW` (lemon 2.3, tangerine and pink and cyan 1.7, lime 1.6) multiplies the centre glow, and `glow_strength(theme, base)` (capped at 0.92) is used by every background: the Shorts frame (`puzzle_fit._themed_background`), the 3D covers (`covers.background`), the long-form frame and thumbnails (`longform._landscape_background`, `longform_cover._background`). Covers therefore always match their video's tone. To make a tone livelier or calmer, change its `THEME_GLOW` or glow colour in `config.py`. Cube colours that would blend into a tone are listed in `THEME_CLASHING_CUBES` (vivid tones included). The Brain Test thumbnail palettes include lemon and cyan.
- The creator chooses the tone in the UI (`Arka plan rengi`). `Rastgele` (the default) draws one from every tone with equal odds (`fresh_theme_for(puzzle_type, seed)`) and **stores it in the spec's metadata** (`background`), so a video keeps its tone however the pool grows. Older videos that never stored a tone still get theirs from `dark_theme_for(puzzle_type, seed)`, whose pool is frozen (`LEGACY_THEME_CHOICES`, the seven classic tones), so re-rendering an old video never changes its colour. Either way the tone is never per round and identical for all of a video's frames and its cover (`palette.background_for`).

## Creator colour choices (all dark-theme games)

`puzzly/palette.py`. The UI offers two boxes next to each other: `Arka plan rengi` (Rastgele or one of the twelve tones) and `Nesne paleti` (Klasik, Neon, Pastel, Mücevher tonları). The choices are stored in `VideoSpec.metadata` (`background`, `palette`), outside the fingerprint like music, and saved with the spec so a Final re-render matches; the default palette (`classic`) is not stored, and `random` is resolved to a concrete tone that is stored (see above).
- A palette keeps each object colour's hue and changes only its saturation and brightness (`recolor`), so colour names stay true (for example `BLUE SURVIVES`) and colours stay as distinct as before. Warm/cool palettes are deliberately not offered because they would change hues.
- It applies to the objects of every Puzzly for You game: shape tokens (`token_image`), balls (`ball_sprite`), cubes (`face_colors`, `cube3d`), Puzzle Fit artwork, Find the Exit portals, and Lucky Pick glows, rings, bands, and bursts, in frames and covers. `use_theme(spec)` activates it; cached layers painted with object colours include the palette in their cache key.
- Memory Challenge keeps its own colours (its colour-similarity levels are part of the game). Light-theme games ignore both choices, and the UI says so.
- Cube Count receives the chosen tone at generation so its cube colours avoid clashing with it.
- `render_frame` calls `use_theme(spec)`. The shared `_background` draws the active tone (gradient plus glow), and every cached background layer takes the theme as part of its cache key.
- Cards, accents, and timers keep the shared palette.
- Missing Operators keeps its own fixed teal and amber palette.

## Per-video 3D covers (all dark-theme games)

`puzzly/covers.py` replaces the old hook-frame JPG covers for every Puzzly for You game: Puzzle Fit, Find the Exit Hard, Cube Count, Memory Challenge, Quick Math (both formats), Lucky Pick, and Bounce Arena. `render_cover` uses the template whenever `has_template(spec)` is true; other games keep the hero-frame cover.
- Every game has one fixed 3D template:
  - the small brand;
  - an extruded two-line 3D title (for example `QUICK` / `MATH` or `CUBE` / `COUNT`);
  - a spaced subtitle;
  - a tilted card that leans back, with a slab edge, a floor shadow, and a rim glow (short cards are centred);
  - 3D floating objects: four blurred ones in the margins and two sharp ones hugging the card corners;
  - a CTA pill and a short line.
- Covers never state a time (no seconds in the title, subtitle, CTA, or line), because thinking and viewing times change by level and difficulty. Cube Count's CTA is `BLINK AND YOU MISS IT.` and Memory Challenge's is `TRUST YOUR MEMORY?`.
- The card holds the video's own level-1 puzzle, so a small spoiler is accepted:
  - Quick Math redraws its level-1 shape board or missing-sign board in 3D (the answer stays `?`).
  - Lucky Pick (snake chase) shows the targets at their start positions as 3D tokens and a staged snake rising from its den (`snake_board`), never a moment of the chase, so it cannot hint at the first victim. Earlier maze videos redraw their maze in 3D (`lucky_board`).
  - Find the Exit Hard redraws its level-1 maze in 3D (`maze_board`): extruded lit walls, star/moon/sun portal coins, and a glossy start orb, never the route. Its copy is `3 EXITS.  1 WAY OUT.`, `CAN YOU ESCAPE?`, and `N MAZES · EACH ONE LONGER`; its floaters are the three portal coins.
  - The remaining games cut their level-1 board from the video's own frame (`CROPS`); Cube Count and Memory show the real first board.
- Colours: the background (gradient, glows, a perspective floor grid, bokeh) uses the video's own tone, `dark_theme_for(puzzle_type, seed)`, so cover and video always match. Missing Signs keeps teal and amber. Floating objects come from the video (its shapes, cube colours, targets, balls, or sign tiles).
- A cover is drawn at 2x and downsampled to 1080×1920 in about 4–9 s. It is saved as the video's JPG with the unchanged filenames.

## Puzzly for You end card (all dark-theme games)

`draw_puzzle_fit_outro` in `puzzly/visuals/puzzle_fit.py` is the one call every Puzzly for You game makes for its end card (Puzzle Fit, Find the Exit Hard, Cube Count, Memory Challenge, Quick Math, Lucky Pick, Bounce Arena, Line Follow, Flash Count, Matchstick Math, Cup Shuffle); it delegates to `draw_end_card` in `puzzly/visuals/end_card.py`. It is built for viewers who do not read, and the user asked for a showier, longer card that also shows the social accounts.
- Length: 3.6 s (`PUZZLE_FIT_OUTRO_DURATION`; Bounce Arena `BOUNCE_CTA_DURATION` 3.7 s), 2 s longer than the earlier 1.6 s / 1.7 s so viewers can read it and follow. Bounce Arena's `MAX_VIDEO_DURATION` grew from 30 to 32 s by the same 2 s, so its simulation window (9–21.8 s) is unchanged. Validation accepts 1.2–4.0 s for these games and each Bounce record's stored `cta_duration`, so older videos still validate; manifest-only records made before 2026-09-30 are rebuilt with the old lengths. Games with no end card (Chess, Hidden Motion Hunt) and the legacy light-theme games are unchanged.
- Accounts: `SOCIAL_HANDLES` in `puzzly/config.py` (change the handles there): a YouTube row (drawn red play-button icon) and an Instagram row (drawn gradient camera icon), each followed by the handle (`@puzzlyforyou`), in a glass panel. Under the panel, a large `FOLLOW FOR MORE` button.
- Timeline: 0–0.5 s the score ring fills (score `?/N`, or the winner for pick games via `hero=`) with a confetti burst; 0.35–0.65 s `COMMENT YOUR SCORE` (or the pick game's short question in capitals) with a bobbing chevron; 0.5–0.85 s the panel slides in, then the YouTube row (0.75 s) and the Instagram row (0.95 s) pop in; 1.15–1.45 s the button rises with a pulsing glow; a finger glides in and taps the `+` icon at 2.0 s (never covering the label): the button presses and flashes, a ripple spreads and a second confetti burst goes off; then it holds with sweeping shine, twinkling sparkles, falling confetti and slowly turning light rays. The channel's round profile photo plus `Puzzly for You` stays small at the bottom: `assets/branding/profile.jpg` (the same picture as on Instagram and YouTube) is cut to a circle from the centred square of the picture, at 4x and shrunk once so the edge is smooth, with a thin rim (`branding.draw_profile_mark`; the generic drawn mark is only the fallback when the file is missing). The same photo is used on the long-form end cards (Brain Test and the Quick Math pilot). Covers and the rest of the videos are unchanged.
- Audio (`end_card` inside `timeline_audio`): a sparkle, a pop for each row (panned left and right), a whoosh as the button rises, a snap and ding on the tap, and a sparkle. Under 1.2 s outros (legacy) only sparkle.
- Themes pass `palette=` and `background=` (for example Missing Operators uses its teal and amber theme). Rendering: about 0.1 s per frame at 1080x1920.
- Tests: `tests/test_end_card.py`.

## Quick Math V8 — Shape Equations, Puzzly for You look

Quick Math now produces formats instead of single equations. The UI's `Format` box (which replaced `Operation`) passes the format through the spec's `operation` field. Implemented formats: `Şekil Denklemleri` (`shapes`) and `Kayıp Operatör` (`operators`). `Zihinden Zincir` (a mental chain) and `Karışık` are planned; `Karışık` changes the format from video to video, never inside one video. The generator is `puzzly/puzzles/quick_math.py` (`legacy_generate` keeps the V7 code). The frames are `draw_quick_math_frame` in `puzzly/visuals/quick_math.py`.

- Each level is a small system of shape equations followed by a question row (`shape + shape × shape = ?`).
  - Every clue introduces exactly one new shape, so the board always has exactly one answer, found step by step.
  - Shape values are distinct integers.
  - The answer is a non-negative integer. It is never a shape's value or a clue's result.
  - The question never contains `x − x` or `x ÷ x`, and in +/− levels no shape both adds and subtracts.
- Levels escalate over tiers 0–3. Default is 3 levels (tiers 0, 2, 3); manual 4 uses 0, 1, 2, 3 and manual 5 uses 0, 1, 2, 2, 3:
  1. 2 shapes, + and −.
  2. 3 shapes, and clues may use ×.
  3. The question has an order-of-operations trap: left-to-right evaluation gives a different number.
  4. ÷ is allowed, and the question has 4 terms and a trap.
  Numbers stay doable in your head: values are 2–12, results and answers are at most 150, and every product has a factor of 9 or less (squares up to 12 × 12). The challenge is the logic and the trap, not long multiplication.
  Rounds in a video use different shape sets and different answers.
- Timing: a 0.5 s staggered row entrance, then thinking that grows with the tier and never exceeds 15 s (Hard 8/10/13/15 s, Medium 9/11/14/15 s, Easy 10/12/15/15 s for tiers 0–3; numeric timer with ticks at 3, 2, and 1). Each round stores its `thinking_seconds`. `VideoSpec.round_duration` holds the average level length, so the total is exact, and the renderer and audio use the real per-level `schedule`. For the last 5 s of thinking, a `⏸ Pause if you need more time` pill fades in at y 1500 to keep viewers who need longer.
- After thinking: 1.05 s of solution chips (`shape = value`, in solving order), a 0.45 s answer pop with a burst, and a 1.0 s hold.
- Screen: `LEVEL n /N` and the timer at the top. The instruction is a large `SOLVE IT.` pill directly above the board card, and the prompt, board, and chips are centred as one group around y 930. During the reveal the pill becomes `SOLUTION`. Trap levels add `Left to right gives N. × and ÷ come first!` under the chips.
- Hook intro (1.0 s): `NO CALCULATOR.`, `N LEVELS · EACH ONE HARDER`, the pill, and the real level-1 board (never its answer). The cover is the game's 3D cover template (see Per-video 3D covers). Outro: the shared Puzzly for You end card (`?/N`).
- Round data stores the format, tier, shapes (shape, colour, value), clues, question terms, and the left-to-right value. They drive fingerprints and manifests (`operations`: `shapes`, `equation_templates`: `shapes_tierN`). Older V7 equation videos keep their legacy validation, but their manifests no longer restore to the new round timing.

### Trap-level help (both formats)

- On trap tiers (2 and 3), a small `× ÷ FIRST` rule badge sits beside the instruction pill. It reminds viewers of the rule without giving the grouping away; parentheses were rejected because they would remove the trap.
- Halfway through the thinking time on trap tiers (`QUICK_MATH_HINT_AT` = 0.5), one clue reveals itself, with a snap sound:
  - Shape Equations shows a `HINT shape = value` chip under the board for the hardest shape, the one unlocked by the last clue (`hint_shape`).
  - Missing Operators flips the first × or ÷ slot open with a green `HINT` tag (`hint_slot`).
  Fast solvers still get the first half at full difficulty; others get a reason to stay.
- Missing Operators never divides a number by itself (no `9 ÷ 9`).

### Kayıp Operatör (`operators`) — teal and amber theme

- Every level shows numbers with empty sign slots (`6 ▢ 2 ▢ 12 ▢ 8`) and the target on its own line (`= 3`). The viewer fills in +, −, ×, and ÷. Every sign combination is enumerated, and exactly one must reach the target (× and ÷ first, only exact division). The target is 0–150. Numbers are 2–12, and every product has a factor of 9 or less. The answer is the sign string (for example `−×÷`).
- Tiers match Shape Equations and use the same per-level thinking times, the pause hint, and the default 3 levels:
  - 0: 3 numbers with + − ×.
  - 1: 3 numbers, with ÷ added.
  - 2: 4 numbers with + − × and an order-of-operations trap.
  - 3: 4 numbers, all four signs, a trap, and always at least one ÷.
  From tier 1 up, at least one × or ÷ is used, and a level never uses the same sign in every slot.
- Look: its own dark teal background (`OPS_PALETTE`: deep teal gradient, teal glow, faint plus-sign grid) with amber accents instead of the violet used elsewhere.
  - The prompt is a large amber `FILL THE SIGNS.` pill directly above the board.
  - Empty slots are dark tiles with a pulsing amber outline and a `?`.
  - A `USE + − × ÷` legend under the board shows the signs allowed on that level.
  - The reveal flips each slot into an amber sign tile in order. The target turns green with a check mark and a burst. Trap levels add the left-to-right note.
  - Hook: `FIND THE MISSING SIGNS.`. The outro is the shared end card in the teal theme.
- Channel covers (1080×1920, 3D look) are in `output/covers_puzzly_for_you/`: `quick_math.png` for Shape Equations and `quick_math_missing_signs.png` for Missing Signs.

## Missing Number V7

- Default 5 rounds with the shared 4.0-second thinking window.
- Use large rounded number cards/capsules with sufficient padding for two-digit values; never use cramped circles. The sequence is the dominant focus inside a centered rounded puzzle card. Calculate complete group bounds and center at x=540 within approximately ±20 px.
- Each sequence has exactly one obvious family: constant addition, constant subtraction, or integer multiplication. Never use alternating/mixed rules.
- Easy is 80% small addition with occasional simple subtraction. Medium balances addition/subtraction and includes controlled ×2. Hard combines larger arithmetic steps with ×2, ×3, ×4, and ×5 geometric sequences.
- Keep every value from 0 through 999, vary internal missing positions, and avoid duplicate sequences and repeated family/rule pairs inside a video.
- Exactly one internal slot is hidden and every answer/pattern is validated.
- Reveal the answer in place with the shared progress timer and success treatment.

## Puzzle Fit V12 — one big picture, three missing pieces (paused as its own video: it plays inside Mind Mix and in the Brain Test)

History: V10 (nine near-identical tiny candidates) did not perform. V11 (three levels, numbered candidates turned by
quarter turns, wrong pieces tried in the hole) was built and rejected before publishing: "still simple"; pieces lying
straight make viewers expect a direct fit, and the wrong-try effect was unwanted. The user chose this format instead,
as one puzzle per video (not three levels). Generator `puzzly/puzzles/puzzle_fit_v12.py` (data `version: fit_v12`,
called by `puzzle_fit.generate`), frames `puzzly/visuals/puzzle_fit_v12.py` (`draw_puzzle_fit_frame` dispatches on the
version), scenes `puzzly/visuals/scenes.py`. `puzzle_fit.legacy_generate` keeps V10 for tests and old records.

- One big 4x3 jigsaw picture (820x615 logical px) of a calm procedural scene: `mountains`, `city`, `sea`, or `dunes`
  (sky gradient, sun or moon, layered silhouettes; drawn locally, no image assets).
- Three missing pieces marked A, B, C: never a corner, never two touching, at least one enclosed (slot 5 or 6). The
  three holes have different shapes even up to rotation, so each missing piece fits exactly one hole.
- Six numbered options (3x2 cards): the three missing pieces and three traps. A trap shows one hole's own picture but
  one or two edges differ (same number of flat sides), so it fits no hole: the picture alone never gives the answer.
- Every option lies tilted 12–30° (so viewers know to turn it in their head); on Hard it is also turned by a random
  quarter turn, on Medium by 0/90/270°, on Easy only tilted. A piece fits when some quarter turn of its edges equals
  the hole's (`rotate`, `fits`); validation checks every hole has exactly one fitting option and no trap fits.
- Answer text `A4 B1 C6` (the RoundSpec answer); viewers are asked to comment in that form.
- Timing (`fit_round`): 0.5 s entrance + thinking (Hard 20 s, Medium 24 s, Easy 28 s, `FIT_THINKING`) + 0.4 s traps dim +
  3 x 0.9 s placements + 0.7 s shine + 1.6 s hold; with the 1.0 s hook and 3.6 s end card a Hard video is ≈ 30.5 s.
- Screen: `3 MISSING PIECES` and the numeric timer at the top; the picture with lettered holes (animated accent dashes);
  a large `FIND THE MISSING PIECES` pill; option cards with big number badges; `Comment like A4 B1 C6 ↓`.
- Reveal (no wrong-try effect): the traps dim; A, B and C fly in one after another on an arc, turn the short way back to
  straight, click (burst) and their cards turn green with `n=A` labels; a light band sweeps the finished picture; the
  answer appears in green (`A = 4 · B = 1 · C = 6`). Hook (1.0 s): the real picture and options under
  `FIND THE MISSING PIECES.` and `3 PIECES · 6 CHOICES`. Outro: the shared end card (`?/3`).
- Cover: 3D template `PUZZLE` / `FIT`, `3 PIECES ARE MISSING.`; the card shows the picture with its lettered holes and
  four tilted numbered options (`fit_cover_card`); `FIND THE MISSING PIECES`, `3 PIECES · 6 CHOICES`; floating number
  tiles. Never marks the answer.
- Audio: card pops, ticks at 3, 2, 1, a whoosh and a snap per placed piece, then ding and sparkle.
- UI: no challenge control (one picture); the caption explains the format. `DEFAULT_ROUNDS["puzzle_fit"] = 1`.
- Tests: `tests/test_puzzle_fit_v12.py`; `tests/test_puzzle_fit.py` keeps testing V10 through `legacy_generate`.

## Puzzle Fit V10 — Puzzly for You pilot (earlier version, kept for old records)

Puzzle Fit is the pilot for the adult "challenge accepted" look. Its dedicated renderer lives in `puzzly/visuals/puzzle_fit.py`; the shared pastel system and the shared intro/outro/dot-indicator rules below do not apply to it.

- Dark theme from the centralized `PUZZLE_FIT_PALETTE`: deep navy gradient, soft violet glow behind the board, faint dot grid near the edges, vignette, dark board card, and a translucent candidate tray. Use the clean Segoe UI/Arial bold UI font, not the handwritten display font.
- Each round cuts one deterministic abstract artwork (`rings`, `stripes`, `lowpoly`, `waves`, `burst`, with a palette from `PUZZLE_FIT_ART_PALETTES`) into bevelled, dark-outlined jigsaw pieces. Every candidate shows the hole's own artwork, so only the shape identifies the answer. Every round in a video uses a different style.
- Hook intro (1.0 s): the first level's real board and candidates are visible from frame one under `ONLY ONE FITS.` and `N LEVELS · EACH ONE HARDER`. Never show the answer. The direct JPG cover is this hook state at `COVER_TIME`.
- Levels escalate within every video and are shown as `LEVEL n /N`. Easy/Medium go 2×2 → 2×3 → 3×3. Hard goes 2×3 → mixed → 3×3, and the final level always uses the enclosed centre hole with no flat edge. Early Easy levels use two-edge decoys; later levels use one-edge decoys.
- Every difficulty uses 5.0-second thinking (`PUZZLE_FIT_THINKING`). Easy/Medium: three candidates. Hard: no corner holes, and nine candidates in a centred 3×3 grid: the answer plus all eight single-edge variants, so every decoy differs from the answer by exactly one edge.
- Timer: a rounded bar below the level header plus a visible remaining-seconds number. It turns from accent to warning (≤50 %) to danger (≤25 %) and pulses in the final 1.5 seconds, with audio ticks at 3, 2, and 1 seconds. This numeric timer is an intentional Puzzle Fit exception to the shared no-countdown rule.
- All candidates float with the same amplitude, differing only in phase, so motion never hints at the answer. Show no correct-answer cue during thinking.
- Round timeline: 0.35 s entrance, thinking, 0.55 s elimination (wrong pieces shrink and drop out in a deterministic staggered order while the answer gains a success glow), a 0.45 s lift-and-fly into the hole, then a snap with a glow, a ring, and a particle burst, followed by a solved hold. Round = thinking + 2.2 s.
- Outro: the shared Puzzly for You end card (see above).
- The empty hole uses a thin (3 logical px), semi-transparent marching dashed outline so its tabs and sockets stay readable.
- Generate local rounded jigsaw tabs and sockets. The hole and the correct candidate use identical geometry. Validate every shared seam, outer edge, candidate, missing slot, answer, level, and art style.
- Keep candidates plausible, with exactly one geometric match and no A/B/C labels.

## Find the Exit — Route Quality Polish

- Auto 4 rounds; Easy/Medium/Hard thinking times 5/6/7 seconds.
- One clear start and three natural symbol-marked boundary exits. Exactly one exit is reachable.
- Generate sparse readable 5×5, 6×6, or 7×7 maze graphs. Three disjoint rooted trees guarantee a unique reachable exit; independently validate connectivity, acyclicity, and the reveal route. Every visible top exit must connect inward immediately, including both false exits, so none is visibly sealed at its icon.
- Build the correct route first with a deterministic loop-erased walk, then grow the three disjoint trees around it. Easy requires at least 3 turns and 1 route branch; Medium at least 5 turns, 1 downward revisit, and 3 route branches; Hard at least 8 turns, 2 downward revisits, and 5 route branches. Difficulty must be visibly meaningful without reducing phone readability.
- Reveal the route progressively from start to exit, then a small positive success indication. Never show answer cards.
- Intro demonstrates a simple start, exits, and route trace.

## Find the Exit Hard V2 — Puzzly for You look

Easy and Medium keep the rules above. Hard uses its own generator (`layout: deceptive_v2`) and its own renderer, `puzzly/visuals/find_the_exit.py`, and shares Puzzle Fit's dark palette, hook intro, level header, numeric timer, and score-question outro.

- Levels escalate inside every video. Level n always uses grid tier n: 10×12 (one sweep, three vertical runs) → 12×14 → 14×16 → 15×18 → 16×20 (two sweeps, five vertical runs) cells (columns × rows). The user asked for bigger, tighter, harder mazes, so every tier grew by about two columns and two rows (it was 8×10 → 10×12 → 12×14 → 13×16 → 14×17). Auto is 4 levels; 3 stop at 14×16 and 5 reach 16×20. Every level is a larger grid, so corridors get narrower (about 40 px between 10 px walls at 16×20) and the answer route longer (minimum about 46 → 68 → 90 → 104 → 118 cells). Every level's answer route is also at least 6 cells longer than the previous level's actual route. The maze fills the logical box x 100–980, y 400–1400. The tiers keep 6, 5, 3, 3, and 2 candidate mazes so generation stays fast (a 16×20 maze takes about 5–35 s; a 5-level video about 40 s), and keep trying past 8,000 attempts until at least one is found. The retired sizes 8×10, 13×16, 14×17, and 9×11 stay valid (`LEGACY_HARD_LEVELS`) so saved records can be re-rendered.
- Thinking time grows with the level: 6, 7, 8, 9, 10 seconds for levels 1–5 (`EXIT_HARD_LEVEL_THINKING`, and `thinking` in each level of `HARD_LEVELS`), stored per round as `thinking_seconds` and validated against the grid size. A grid size keeps one thinking time everywhere (older sizes: 8×10 5 s, 13×16 8 s, 14×17 9 s). Levels therefore last different times: `visuals.find_the_exit.schedule` gives every level's start and duration (used by frames, effects, and music) and `VideoSpec.round_duration` is the average of the levels, so the total duration stays exact. Older rounds without `thinking_seconds` keep 8.0 seconds on every level.
- Construction:
  1. **Snake route.** The answer route snakes through vertical lanes:
     - Edge exits: it works lane by lane from the far side, up, down, up (and down, up at the larger levels).
     - Middle exit: it climbs and dives on one side, crosses underneath, climbs and dives on the other side, then climbs the middle lane.
     - Upper turns stay at 20–42 % of the height, so the top band is left for the false exits. The route always enters its exit from directly below.
  2. **Decoys.** Levels 1–3 have three exits, levels 4–5 four (`exits` per level; a green diamond is the fourth portal). False exits are placed after the route, only in columns where a decoy spine (a winding walk that stops at the first cell at 30 % depth or more) can dive.
  3. **Grow the false regions** (`maze_version: 3`, added after the user showed that a false exit could be ruled out by tracing back from it: its region was only ~20 cells and dead-ended at once). `_grow_decoys` grows every false region with loop-erased walks until together they own `DECOY_QUOTA` (62 %) of the off-route cells. Tracing back from a false exit is then about as long as solving from the start.
  4. **Fill.** A single multi-root Wilson forest seeded by all trees fills the rest. Region borders therefore follow random walks and look like ordinary maze walls.
  5. **Selection.** Several valid mazes are generated per round and the one with the largest smallest decoy region is kept. A 5-level video now takes about 60 s to generate (the straight-wall rule rejects most attempts).
- Validation requires:
  - one tree per exit (3 or 4) and exactly one exit reachable from the start;
  - the route matches the BFS path and meets its level's length, turn, and vertical-run thresholds (at least 3 or 5 alternating up/down runs);
  - every exit has an inward passage straight down;
  - each false region covers at least 6 % of the cells and, in version 3 mazes, at least `MIN_DECOY_SHARE` (60 %) of its fair share of the quota, and reaches at least `DECOY_REACH` (40 %) of the way down toward the start (older records skip these two checks);
  - no interior straight wall is longer than 5 cells (6 on the four-exit levels, which have one more region border), because long unbroken seams give away sealed regions;
  - each recorded decoy end is the deepest false-region cell that touches the route at or below 30 % depth;
  - the route has enough competing branch points.
- Answers are an independent uniform draw per level (`hard_answers`, seed `exit_hard_answers_v3`), fixed before any maze is built, so acceptance rates cannot bias them. Earlier versions dealt shuffled blocks, so levels 1–3 always used three different exits and a viewer could deduce level 3 from levels 1 and 2; after the user noticed a repeating order in published videos, they asked for truly random answers. Repeats (the same exit twice or three times) are therefore allowed. Exit columns vary per round within left, centre, and right bands.
- Timing: per-level thinking (above), 1.6-second glowing route trace, 0.9-second hold (level = 0.35 + thinking + 2.5 s), a 1.0-second hook intro (`ONLY ONE EXIT IS OPEN.`), and the 3.6-second shared end card. Audio ticks at 3, 2, and 1 seconds, then a whoosh, a ding on arrival, and a sparkle.
- Look:
  - Walls are rendered as lit 3D bars: a blurred drop shadow, a vertical gradient body, a bright top-left rim, and a dark lower edge.
  - The floor is a faint checker, softly lit from the exits.
  - Exits are star/moon/sun (and diamond on four-exit levels) portals of equal brightness, so none stands out; they never shrink below a 24 px radius on the tightest grids. The start is a pulsing teal orb.
  - The reveal draws a neon trail with bloom. On arrival, the wrong portals dim and the correct portal gets the ring-and-particle burst.
  - The cover is the game's 3D cover template (see Per-video 3D covers).

## Find the Exit Hard — circular mazes (the user's idea: "the same format as a circle")

Find the Exit Hard has a second maze shape. The UI shows a `Labirent şekli` box when Find the Exit is Hard: `Dikdörtgen` (the default, everything above, unchanged), `Daire`, `Altıgen`, `Yıldız`, `Elmas` (see the next section), and `Karışık (rastgele)` (every level a different shape; a 5-level video uses each of rectangle, circle, hexagon, star, and diamond exactly once in random order, shorter videos draw distinct shapes from the five, and longer ones start the draw over without repeating a shape back to back; difficulty always follows the level, not the shape; `level_layouts`, seeded so a seed always gives the same video; the first versions alternated rectangle and circle, and made videos keep the layouts they stored). `generate_spec(..., maze_shape="rect"|"circle"|"hex"|"star"|"diamond"|"mixed")`; Easy and Medium have no circles. Generator `puzzly/puzzles/exit_polar.py` (data `layout: polar_v1`), drawing in `puzzly/visuals/find_the_exit.py` (`polar_*` functions); everything after the maze (markers, neon trace, timer, hook, end card, audio, music windows) is shared with the rectangular mazes.
- **Layout (the user's rules):** the start is in the MIDDLE (the pulsing teal orb on the centre disc) and the exits are on the rim, spread around the circle: **4 exits on levels 1–3 and 5 on levels 4–5** (`POLAR_LEVELS[...]["exits"]`). Exits are star, moon, sun, diamond, and (new) hexagon (`EXIT_COLORS` has a fifth colour). An exit cell is a leaf that only opens inward, so no exit looks sealed at its portal. Exactly one exit can be reached; the answer is drawn uniformly per level before any maze is built (`layout_answers`).
- **Polar graph:** node 0 is the centre, then rings of sectors: ring 1 has 8, and a ring doubles its sectors when its cells would get longer than 1.55 ring heights (`sector_counts`; for example 5 rings: 8, 16, 16, 32, 32), so corridors keep a similar shape from the middle to the rim. The maze is a forest of one tree per exit (edges = cells − exits), built like the rectangular Hard mazes: the answer route first (a loop-erased walk from the centre through waypoints that send it out, back in, and out again, sweeping around the circle one way and ending at the exit's own angle), then every false exit digs a spine to a ring at least 40 % of the way toward the middle and grows into a region to the shared `DECOY_QUOTA` (62 % of the off-route cells, each region keeping at least 60 % of its fair share), then a multi-root Wilson fill. Several valid mazes are made per level and the one with the largest smallest false region is kept.
- **Difficulty is the number of rings** (the user asked which knob to use): levels 1 to 5 have 5, 6, 7, 8, 9 rings (about 105, 137, 169, 233, 297 cells, close to the rectangular 120–320), so corridors get narrower (ring pitch 75 → 42 logical px) and the route longer. `POLAR_LEVELS` also sets per level the waypoints (out/in ring fractions), `radial_runs` (the route must go out, back in, and out again: at least 3 alternating radial runs, 5 from level 3), `min_route` (22, 30, 42, 56, 70 cells; a level's route is also at least 4 cells longer than the previous circular level's), `route_branches`, and thinking time (6, 7, 8, 9, 10 s, the same as the rectangular levels, stored per round as `thinking_seconds`, so durations and `schedule` are shared). No unbroken wall arc may exceed 150° (`MAX_ARC_WALL`), because long seams give away sealed regions. Generation takes about 1–3 s per level (20 s for a 5-level video).
- **The middle has exactly one opening** (the start's only passage leads to the route's first cell), and the start is shown unmistakably (the user found the plain three-cornered triangle hard to read as a direction): the orb holds a real arrow, a shaft with a wide head, pointing at that opening (`_start_orb(heading=, arrow=True)`; rectangular mazes keep their upward triangle) (the user later removed the animated chevrons that ran outward through the opening: the arrow alone is clear enough, so there are none). The start therefore shows where the maze begins without giving the route away.
- **The neon trace follows the corridors** (`_polar_route`): it runs along a ring or straight along a radius (never a diagonal cut between cell centres), slides to the outer cell's angle first when the sector count doubles, cuts any spike where it would run into a cell and straight back out (`_drop_reversals`), is sampled every 8 px, and has its corners rounded (`_smooth`, a moving average with the ends fixed).
- **Validation** (`exit_polar.errors`): the middle has one opening, rings and sectors (equal or doubling), start 0, 3–6 rim exits, passages join adjacent cells, one tree per exit, no cycle, exactly one reachable exit equal to the answer, the stored route equals the tree path and meets its stored `rules` (so retuning `POLAR_LEVELS` never invalidates a made video), every exit opens only inward, false regions large and deep, arc wall limit, branch points.
- **Look:** a round plate (radius 508) behind the maze (radius 430, centre (540, 905)), faint annular checker cells, 3D lit arc and radial walls (the same gradient, rim, and shadow as the rectangular walls; arcs are drawn as merged polylines at 2x), exit glows around the rim, portals outside the rim, and the neon route trace bent along the rings. The cover for a circular first level is the real level-1 plate cut from the frame (`CROPS["find_the_exit_circle"]`) with `N EXITS.  1 WAY OUT.`.
- **Level captions (the user's request: the screen below the maze felt empty):** every Find the Exit Hard level, rectangular or circular, shows one short line under the maze that eggs the viewer on, while thinking, fading in after 0.5 s and out as the trace sets off: `Warm up. Stay sharp.` (first level), `A little trickier now.`, `Don't trust the first path.`, `More exits. More traps.`, and `Last level. Make it count.` (the last level); videos with fewer levels use the first, the last, and the middle lines in turn (`CAPTIONS`, `level_caption`). Quiet white text with a soft shadow at 54 px, centred just below the plate or card (`caption_y`), never a pill, so it motivates without crowding. No statistics or claims. The Brain Test turns it off (`metadata["captions"] = "off"`), because the long video has its own panels.
- Tests: `tests/test_exit_polar.py`.

## Find the Exit Hard — shaped mazes: hexagon, star, diamond (the user's request after Find the Exit outperformed every other game)

The Instagram statistics showed Find the Exit as a huge outlier (347K, the circle 59.7K, another 24.6K views against 4–9K for Line Follow, Missing Signs, and Bounce Arena), so the user asked for more "trace it with your eyes" formats. The maze-shape box (`Labirent şekli`) now also offers `Altıgen`, `Yıldız`, and `Elmas`, one at a time, and in `Karışık (rastgele)` they appear with the rectangle and the circle (see the circular section). A spiral was proposed but dropped: it cannot satisfy "start in the middle, exits on the rim, big deep false regions"; the diamond (a rotated square grid) took its place. A triangle was built and then removed at the user's request (do not re-add it); the user liked the hexagon, star, and diamond. Generator `puzzly/puzzles/exit_shapes.py` (data `layout: cells_v1`, `maze_version: 1`), drawing `is_cells`, `cells_*`, `_cells_layer`, `_draw_cells_markers`, and `_cells_route` in `puzzly/visuals/find_the_exit.py`.

- Everything the circular maze promises carries over: the shape is inscribed in the same round plate (maze radius 430, plate radius 508, centre (540, 905)); the start orb sits in the middle cell, which has exactly one opening, with the arrow pointing at it and the chevrons; 4 exits on levels 1–3 and 5 on levels 4–5 (`TIERS[...]["exits"]`), as leaf cells that open only inward; exactly one exit is reachable; a forest of one tree per exit (edges = cells − exits); the answer route is a loop-erased walk through waypoints that send it out, in, and out again; false exits dig spines at least 40 % of the way toward the middle and grow regions to the shared 62 % quota (each at least 60 % of its fair share and at least 6 % of all cells), then a multi-root Wilson fill; thinking 6, 7, 8, 9, 10 s; level captions; the shared hook, timer, end card, audio, music, and neon trace.
- Cells are polygons with shared-edge adjacency (`Layout`: `polygons`, `adj`, `shared`, `outer_edges`, `rim`, `depth`, `gate`, `inward`). Difficulty is the size (`SIZES`, level n uses size n and tier n−1): hexagon 5–9 rings (91, 127, 169, 217, 271 cells), star 3–6 (108, 192, 192, 300, 432), diamond 9–17 (81, 121, 169, 225, 289). A made video stores its shape, size, `rules` (`min_route`, `runs`, `bands`, `route_branches`, `false_share`, `max_straight`), and `thinking_seconds`, so retuning `TIERS` never invalidates it.
- **No round plate (the user's request: the circle behind the hexagon, star, and diamond looked wrong):** each shaped maze sits in a frame in its own shape (`_cells_frame`: the cells and exit portals grown by 20 px with round corners, a surface fill, an edge line, and a soft shadow); only the circular maze keeps its circular plate.
- Walls are two-point polylines (`cells_walls`, `_polyline_mask`) lit like the other mazes; the route runs through cell middles (dense 8 px steps, `_smooth`). No unbroken straight wall may exceed `MAX_STRAIGHT` (99 cells for the hexagon, 6 for the star and diamond), because long seams give away sealed regions.
- Validation (`exit_shapes.errors`): known shape and size, the start's single opening, exits clockwise by angle, one tree per exit, no cycle, exactly one reachable exit equal to the answer, the stored route equal to the tree path and meeting its stored rules, false regions large and deep, straight-wall limit, branch points. Generating a level takes about 1–5 s.
- The cover is the real level-1 plate cut from the frame (`CROPS["find_the_exit_circle"]`).
- Tests: `tests/test_exit_shapes.py`.

## Line Follow — Weave V8, a board full of long same-colour cables, Hard only (current)

The user found every earlier version too simple and its lines broken-looking (braid; Tangle V3 short Catmull-Rom lines; Tangle V4 wobbly 8 px random walks with gap-cut bridges). Weave V5 (tidy lines from every target to a row of sockets) was judged too empty: "fill the screen, the lines must be much longer and wander everywhere", and only the correct line may start at the bottom so the viewer never wonders where to begin. Weave V6 did that and was liked, but its level 5 was "a bit short for level 5": the figure's line must get longer level by level, at level 5 at least 1.5 times V6's (V6 drew about 3.6k–5.4k px there), the other lines must grow with it, and both must fill the board with no meaningless empty space. Do not bring any of the earlier versions back. Rules from the user: produced only in Hard, levels 1 to 5 get harder, even level 1 is not easy, the board is as full as possible, only the figure's line reaches the bottom, the lines get longer every level.

Weave V8 (user request): levels 1 to 5 have 4, 5, 5, 6, 6 targets and lines (a later level must never have fewer objects than an earlier one), the board gets fuller level by level, and thinking is 5, 6, 7, 8, 10 s.

Generator `puzzly/puzzles/line_weave.py` (data `version: weave_v8`, called by `line_follow.generate`), frames `puzzly/visuals/line_follow.py`. The UI shows a locked `Hard`; any requested difficulty gives the same Hard video, and filenames end in `_hard`. Auto is 5 levels (3 and 4 are supported: 3 use tiers 0, 2, 4).
- Board: target portals across the top (star, moon, sun, diamond, ring, heart, triangle), one line each: 4, 5, 5, 6, 6 at levels 1–5. Under the readability rules the board holds at most about 18–20k px of line, so the six-line levels share it: their other lines are shorter than level 3's, while the figure's line keeps growing and crosses more lines. Only the figure's line (always the first line in the data, stored from the figure up to its target) reaches the bottom row, where the figure stands at a random x; every other line ends at a plain rounded loose end, at least 150 px from the figure and never below y 1400. The answer is never the target nearest above the figure.
- Lines are uniform cubic B-splines stored as control points (tripled ends, a vertical lead out of the figure and into the targets), sampled every 5 px. They are grown one at a time, control point by control point (`Grower`), always heading for the emptiest room they can find (`_pick_goal`: of 36 random spots 230–950 px away, at least 90 px inside the sides and bottom and 130 px under the top band, the one farthest from any line), so they reach the corners too. The figure's line is grown first, from the figure: it keeps the strip under its target free while it wanders, keeps one self-crossing in reserve, and once its length budget is used (or, if it runs out of room, once it has 90 % of it: `EARLY_HOME`) it climbs to a gate under its target and straight up the target's chimney. Then each other line grows down from its target and ends as soon as its tip is clear after its length (or after 70 % of it, `MIN_DECOY_SHARE`, if it runs out of room). Each new control point finalises a piece of curve that `Tracer` checks at once; a line backs up when stuck (each dead end in a row backs up twice as far), restarts, and a round takes the previous line off (`Board.pop`) when one cannot be placed. Lines only move down through the band under the targets (y < 540), and every target keeps a clear chimney under it.
- Readability rules (the same `Tracer` replays them in `validate`): two lines closer than 18 px must be crossing there (lines are 7.5 px wide, so a gap is always over 10 px); every crossing at least 36°; crossings at least 32 px apart; the same two lines never cross twice within 2.5 crossing windows; turning radius at least 30 px (in practice about 115 px); no line within 40 px of another line's end or of a target's chimney; self-crossings per line at most 5, 6, 8, 8, 10 for the figure's line and 2, 3, 3, 4, 4 for the others.
- Tiers (`TIERS`): lines 4, 5, 5, 6, 6. The figure's line budget is 2800, 4300, 5200, 5400, 6000 px (`validate` requires at least 90 % of the budget). The other lines are 2.4k–3.0k, 3.0k–3.7k, 3.3k–4.0k, 2.4k–3.0k, and 2.6k–3.2k (`validate` requires at least 70 % of the tier's lower bound). The figure's line crosses other lines at least 11, 18, 22, 24, 28 times, and every other line crosses it. Board coverage (40 px cells below y 540 and away from the figure, with a line within 44 px) is at least 66, 73, 76, 77, 78 %.
  - Measured density rises level by level: total line about 12.1k, 17.4k, 17.6k, 18.1k, 19.0k px; coverage about 69, 82, 83, 82, 85 %; the figure's line crosses others about 15–27, 27–39, 36–45, 42–48, 38–51 times.
  - Thinking is 5, 6, 7, 8, 10 s (`LINE_THINKING`). A level lasts 0.35 + thinking + 2.4 s trace + 0.9 s hold, so a 5-level video runs about 57 s with its intro and end card.
  - Weaving a level takes about 1 s at level 1 and a median of about 25 s at level 5, occasionally a few minutes (`generate` is cached per seed). Denser six-line settings fail to weave within minutes.
- Older records: `weave_v7` (5, 5, 5, 4, 4 lines; 7, 9, 11, 13, 15 s) still validates and renders through `TIERS_V7` and `LINE_THINKING_V7` (`tier_table`, `thinking_table`; `is_weave` recognizes both versions).
- Look: shared dark background, card, header, numeric timer, and end card. Cables are all the same colour: a 7.5 px light core with a 12.5 px dark casing and a soft bloom, drawn at twice the frame size and scaled down. At every crossing a coin flip per crossing decides which line is on top, and that line's piece is redrawn with its casing, so over and under read clearly without cutting gaps and no line is always underneath. The figure is a glowing teal head-and-shoulders pictogram. Reveal: a neon trail traces the figure's line up to its target, the other targets dim, and the correct one gets the ring-and-particle burst.
- Hook intro (1.0 s): level one's real board (no answer) under `WHERE DOES IT LEAD?` and `N LEVELS · EACH ONE HARDER`. Cover: the 3D template (`LINE` / `FOLLOW`, `FOLLOW THE LINE.`, `WHERE DOES IT END?`) with a board of its own woven from the video id (`COVER_TIER`), never one of the video's boards.
- Music: tense, 100 BPM, A or E minor, harp arpeggios. Older `tangle_v4` samples still validate (`line_tangle`, with `LINE_THINKING_V7`) but can no longer be rendered; `weave_v5` and `weave_v6` records can no longer be validated or rendered.

## Line Follow V8.1 (earlier light-theme version, kept for old records)

- Auto 4 rounds; Easy/Medium/Hard thinking times 5/6/7 seconds.
- Easy uses 3 paths and 2 controlled crossings; Medium uses 4 paths and 6 crossings; Hard uses 5 paths and 12 crossings. Every path has one top anchor, one unique destination, and meaningful interaction with the route group.
- Build routes as C1-continuous floating-point cubic Bézier segments with shared vertical tangents at stage boundaries. Adaptively subdivide by curvature and a 5-pixel maximum chord; quantize only at the final high-resolution raster boundary.
- Rasterize only the Line Follow path crop at 4× Final resolution. Draw one continuous joint-smoothed centerline with round end caps only, then downsample with LANCZOS into the existing 2× Final composition. Never stamp a circle at every sampled vertex.
- Every crossing is a deliberate bridge: a short clean surface halo clears only the underpass, then a substantially longer top centerline reconnects to untouched base stroke on both sides. Foreground and halo must never share endpoints; the top path must have no centerline or bridge-end gap.
- Hard requires at least 8 target crossings, three lane spans, three direction changes, three interactions for every visible path, and interaction with at least three distinct decoys. It also requires at least four target interactions below mid-height, two in the final third, two in every vertical third, no target idle run longer than two stages, and at least one lower-half interaction for all five paths. All exits remain structurally plausible late into the puzzle.
- All lines use the same neutral appearance during thinking. Only the designated source is highlighted.
- Validate the source, permutation of destinations, every overpass, bounds, deterministic routing, and correct answer.
- Reveal by tracing the designated line and marking its destination. The intro demonstrates this without instructions.

## Memory Challenge V8 — three levels (paused as its own video: its hardest level plays inside Mind Mix, and it plays in the Brain Test)

The user found the single-board Memory "lifeless and static" (seven seconds of nothing moving, then eight identical questions, flat cards, childish shapes) and asked for a livelier version. It is now three levels in one video, produced only in Hard (the UI shows a locked `Hard`; filenames `PZ_XXXX_memory_challenge_hard`). Generator `puzzly/puzzles/memory_levels.py` (data `version: memory_v8`, `layout: levels_v8`; `memory_challenge.generate` makes it by default, `classic=True` makes the earlier board), frames `puzzly/visuals/memory_levels.py`. Everything is tuned in `MEMORY_LEVELS` in `config.py`; a made video stores its own `memorize_seconds`, `thinking_seconds`, and question count, so retuning never changes it (`memory_level_round`, `memory_average_round`, `memory_levels_total`).
- **Levels** (the board grows and the question changes; `MEMORY_LEVELS`): 1) a 2×2 board (4 shapes), memorize 3 s, `where` with 2 questions of 2.5 s; 2) a 3×2 board (6 shapes), memorize 4 s, `vanish` with 2 questions of 3.5 s; 3) the full 3×3 board (9 shapes), memorize 5 s, `where` with 3 questions of 3.0 s. A default video lasts about 56 s (levels about 12.7, 15.6, 19.9 s; 4.0 s hook + READY and 3.6 s end card). Score: 7 questions (`?/7` on the end card; the Brain Test awards one point per level).
- **`where`:** the face-up board bobs gently while the timer bar runs (`MEMORIZE` pill, bar only, no seconds), the cards flip face down to numbered covers, and for each question the shape to find sits in a glowing card under the board (`WHERE WAS IT?` pill, numeric timer, dots show the question). The answer card lights green and flips; opened cards stay open. After the last question the remaining cards flip open with a burst (`ALL n.`).
- **`vanish`:** the board stays face up; one card shrinks away and leaves a dark socket with a number and a pulsing `?` (`WHAT VANISHED?`, numeric timer). The viewer names the shape that is gone (the other cards stay visible). The card pops back with a green glow and a burst (`THERE IT IS.`). After the last question the board holds complete (`SHARP EYES.`).
- **Look:** big glossy 3D cards on a slab with a soft shadow, as large as the screen allows (`grid_layout`: 330 logical px on the 2×2 board, 272 on the others, up to 880 px wide; the earlier cards were 250), a vivid violet gradient on the face-down covers, dark faces with a colour halo and a gloss stripe, pill and `LEVEL n /3` header like the other games. The shapes are plain geometry only: circle, triangle, square, diamond, hexagon or pentagon (never both), cross, and three new ones (ring, semicircle, parallelogram); no hearts, moons, or stars. Every shape and every colour on a board is different. The creator's colour-similarity choice (`Renk benzerliği` 1–4) still applies (a subset of the palette of that level); the object palette never applies. The background tone applies, so the vivid tones work here too.
- **Hook** (1.0 s): a fixed concept board of numbered covers with three demo shapes (`REMEMBER IT ALL.`, `3 LEVELS · EACH ONE BIGGER`), never a real level; then the 3.0 s READY screen (`You will memorize the shapes.`; the earlier board says `9 shapes`). **Cover:** the standard 3D template (`MEMORY` / `CHALLENGE`, `REMEMBER IT ALL.`, `TRUST YOUR MEMORY?`, `N LEVELS · EACH ONE BIGGER`) with the hook's concept board on the card (`CROPS["memory_levels"]`) and floating tokens of the last level.
- **Audio:** card pops, ticks over the last 3 s of the memorize window, a whoosh as the cards flip (or the first card vanishes), a pop and a tick before every answer, a snap and a ding when it lands, and a sparkle at the end of the level. Music: the same calm music-box style as before, with one memorize window per level and one window per question (`_windows`).
- **Validation** (`memory_levels.errors`): version, kind (`where` or `vanish`), a 2×2/2×3/3×2/3×3 board with a token per card, unique supported shapes, unique valid colours that meet the level's minimum OKLab distance and brightness, ordered positions, distinct question positions (at most n−1), an answer equal to the questions, and timing in range; the video needs tiers 0, 1, 2, boards that grow level by level, and the average round duration.
- Tests: `tests/test_memory_levels.py`.

## Memory Challenge V7 — 3×3 grid, Puzzly for You look (earlier version, kept for old records and tests)

Single-board game; Easy/Medium/Hard. The generator is `puzzly/puzzles/memory_challenge.py` and the frames are `draw_memory_frame` in `puzzly/visuals/memory.py`. It shares the dark palette, the numeric timer, and the score-question outro. The shape helpers (`token_image`, `shape_mask`) are still shared with Lucky Pick and Hidden Motion Hunt, so new shapes may only be added, never altered.

- A 3×3 grid of nine unique shapes. The pool is `MEMORY_SHAPES`, the eight classic shapes plus cross and moon. Pentagon and hexagon never share a board. Each shape has one colour from the difficulty's nine-colour palette.
- Colour similarity is a separate UI choice (`Renk benzerliği`, 1–4), shown only for Memory Challenge and passed to the generator as the `colors_N` theme; the level is stored as `color_level` in the board data. The higher the level, the closer the colours (`GRID_PALETTE_IDS`, checked with OKLab):
  - 1 (default, also used by Mixed mode): nine distinct hues such as yellow, orange, blue, green, and pink (minimum distance 0.10, average 0.24 or more).
  - 2: three shades in each of three families (minimum 0.05, average 0.20 or more).
  - 3: nine neighbouring hues from one half of the colour wheel with varied lightness (minimum 0.07, average 0.16–0.20).
  - 4: nine close shades of one family (minimum 0.035, average 0.10–0.15).
  - Every colour has lightness 0.55 or more, so it stays bright on the dark cards. Older manifests without `color_level` are validated against the level whose palette holds their colours.
- Difficulty sets the memorize time: Easy 8 s, Medium 7 s, Hard 7 s. While memorizing, only the progress bar shows (no seconds number); questions keep the numeric timer.
- Timeline:
  1. 0.3 s: card pop-in.
  2. Memorize, with a `MEMORIZE` header and a numeric timer.
  3. 0.6 s: staggered flips to numbered violet covers.
  4. Eight timed questions, each 0.25 s entrance, 3.0 s thinking, 0.25 s green highlight, 0.45 s flip, and 0.2 s hold. The header reads `QUESTION n /8`, and the target token sits in a glowing card under `WHERE WAS IT?`. Revealed cards stay open.
  5. The ninth position is never asked: after 0.4 s it flips open by itself (`LAST ONE`), then the full board holds for 1.25 s (`ALL 9`).
- The hook intro is 1.0 s (`REMEMBER ALL 9.` and `8 QUESTIONS · N SECONDS TO MEMORIZE`), followed by the 3.0 s READY screen (`You will memorize 9 shapes.`). It uses a fixed concept grid of numbered covers and three demo tokens, never the real board. The cover is the game's 3D cover template (see Per-video 3D covers). The outro is the shared 3.6 s end card with `?/8`.
- Store the nine shapes, colour ids and values, positions 1–9, the eight-question order, the final automatic position, the memorize seconds, the colour level, and the palette variant in the spec and manifest. They drive fingerprints and history.
- Earlier five-token (V6) manifests cannot be re-rendered with the grid renderer.

## Flash Count V10 — number flash, Puzzly for You look

The user replaced the old shape-counting Flash Count completely: a number flashes for a split second, the viewer has 3 s to recall it, then the number is shown. Same name (`flash_count`), same slot in the selector and the Mixed pool. Generator `puzzly/puzzles/flash_count.py` (data `format: number_flash`, `version: number_flash_v1`), frames `puzzly/visuals/flash_count.py`. Old token-counting (V9) records can no longer be rendered.
- Produced only in Hard (the user's rule): the generator always makes Hard videos whatever difficulty is passed, and the UI shows a locked `Hard`. The number stays on screen 0.2 s (6 frames at 30 fps), and 0.3 s (9 frames) on 6-digit levels (`FLASH_VISIBLE`, by digit count). Levels grow within every video by digits (`FLASH_DIGITS`): 4, 5, 6 digits on the opening, middle, and final tier (the Cube Count split: tiers 0, 0, 1, 2 for 4 levels; 0, 1, 2 for 3; 0, 0, 1, 2, 2 for 5).
- Numbers are read, not recognised: no leading zero, no repeated neighbours (55), no counting runs of three (345, 987), no digit more than twice, and never the same number twice in a video.
- Level timeline (every phase is a whole number of frames): 0.9 s GET READY (empty slots, one per digit, under pulsing focus brackets) → the number flashes (plain white digits in the slots, no animation) → straight to 3.0 s thinking (the user had the random-bar mask after the flash removed; do not bring it back) (`?` in every slot, numeric timer, `What was the number?`) → 1.0 s reveal (digits drop into their slots one by one, violet) → 0.9 s hold (all slots turn green, burst, `Did you get it?`). Every level lasts 6.1 s; a 0.2 s flash leaves a 0.1 s longer hold.
- Intro (4.0 s, `FLASH_INTRO`): the 1.0 s hook (`BLINK AND YOU MISS IT.`, `N LEVELS · ONE BLINK EACH`) and the shared READY screen (see below: `You will read a number.`, `ARE YOU READY?`, a 3-2-1 countdown), then the first level starts (it was a 2.0 s `ARE YOU READY?` screen). Cover: the 3D template (`FLASH` / `COUNT`, `READ IT IN A BLINK.`, `WHAT WAS THE NUMBER?`) with its own random 4-digit number (`cover_number`, seeded by the video id, never one of its levels) and random floating digit tiles, so nothing from the game is spoiled; no time on the cover. Outro: the shared score-question end card.
- Audio: a shutter click on the flash, a whoosh on the mask, clock ticks over the last 3 s, a pop per revealed digit, then ding and sparkle. Music: tense, 108 BPM, E or D minor, a vibraphone lead with its own motif.
## Cube Count V1 — Puzzly for You look

Active standard puzzle type (Easy/Medium/Hard, default 4 rounds, manual 3/4/5, part of Mixed mode). Generator `puzzly/puzzles/cube_count.py`, renderer `puzzly/visuals/cube_count.py`; shares Puzzle Fit's dark palette, hook intro, level header, numeric timer, and score-question outro.

- **Formats (the user's idea: "every level counts differently"; `mode` in every round, `CUBE_MODES` by level count).** A default 4-level video is `grid` (the classic flash below), `rain`, `sweep`, `rain_color`; 3 levels: grid, sweep, rain_color; 5 levels: grid, rain, sweep, grid (tier 2), rain_color. `generate(..., formats=False)` and older rounds (no `mode`) are the all-`grid` classic. Each level has its own length (`config.cube_round(data)`, `visuals.cube_count.phases(item)` / `schedule(spec)`), and `VideoSpec.round_duration` is their average (`cube_average_round`), so the total stays exact. A default Hard video is about 46 s (levels about 6.8, 9.8, 9.3, 12.5 s) plus the 4.0 s hook + READY and the 3.6 s end card.
  - **SPEED IS TUNED IN ONE PLACE** (the user retunes it after watching): `CUBE_RAIN` (`interval` between landings, `fall` of one cube; Hard 0.24 / 0.45 s), `CUBE_SWEEP` (seconds for the train to cross; Hard 2.8 s), `CUBE_RAIN_MIN_GAP` (0.15 s), `CUBE_REPLAY_SPEED` (2.0), `CUBE_RAIN_SOUND` (a soft tick as each cube lands; on in Easy/Medium, off in Hard because it would count for the viewer). A made video stores its own `fall`, `interval`, `rain_seconds`, and `sweep_seconds`, so retuning never changes existing videos and validation accepts `CUBE_FALL_RANGE` / `CUBE_SWEEP_RANGE`.
  - **Rain** (`rain`): cubes fall one by one from under the level header onto random cells of the 6×6 board (streak, gravity, landing flash), then vanish over 0.28 s, so nothing stays to count afterwards. One big block falls too and counts as ONE cube. Totals Easy 7–9, Medium 9–12, Hard 11–15. Cubes in the air or fading together are at least a cube apart on screen (`apart_on_screen`), and landings are at least 0.15 s apart. After 3 s of thinking the rain replays at 2× with a number over each cube and a running total (`How many cubes?`, green total, burst).
  - **Sweep** (`sweep`): a train of 5 towers (4 on Easy; heights 1–3, up to 4 on Hard; mixed heights, never a staircase) and one big block rides a conveyor belt left to right across the screen, entering and leaving off-screen at constant speed (fully in view for only about 0.3 s in Hard). Drawn on a finer 8×8 floor lane (`sweep_geo`, `sweep_stacks`). Totals Easy 6–8, Medium 8–11, Hard 10–14. The answer parks the train in a row centred on the screen and counts it tower by tower, left to right, with labels.
  - **Colour rain** (`rain_color`): before the level starts, the counted colour is introduced for 2 s (`CUBE_TARGET_INTRO`, stored per round as `intro_seconds`, so `cube_lead(data)` and the level's length come from stored data): the `COUNT ONLY` chip sits big in the middle over a dimmed board and its cube zooms in and out twice, then the chip glides up to its place as the level begins (audio: a pop per swell, a whoosh). The rain with three colours from three different hue families (`HUE_FAMILY`: blue/violet, green/teal, yellow/amber, red/pink, so no two can be mistaken) of which only one counts. A `COUNT ONLY` chip with a swatch cube of the counted colour stays on screen. Hard 14–18 drops, 5–8 of them counted, every colour falls at least twice. In the answer replay the other colours fade dim and only counted cubes are numbered.
  - Every level in a video has its own cube colour (never the same twice in a row, avoiding the background tone). The intro subtitle is `N LEVELS · N WAYS TO COUNT`; the cover and the READY screen are unchanged.
  - Tests: `tests/test_cube_count.py` (formats, drop spacing, colour families, sweep train, stored-timing retuning, frames, audio).
- Big blocks (the user's addition, `version: 2` rounds; the classic `grid` level): besides the one-cell towers, every level has exactly one big block (`size: 2`), a single box on a 2×2 footprint and one cube tall, with no inner edges, that counts as ONE cube (a hurried viewer counts four). It never carries cubes on top and keeps the same spacing from every tower (`spaced_stacks`). It needs room, so version 2 boards are one cell larger (`GRID_BIG`: 5×5 on Easy, 6×6 on Medium/Hard); the count reveal labels it `1`. Painter order uses `stack_order` (axis-separation first, then centre). Older rounds without `version` keep their 4×4 / 5×5 boards and still validate.
- An isometric board: 4×4 on Easy and 5×5 on Medium/Hard (older rounds; see big blocks above for the current sizes). Stacks are 1–3 cubes tall; Hard's final level allows 4-cube towers and always includes at least one. Stacks obey gravity and occupy distinct cells. Every round picks its own cube colour from `CUBE_ROUND_COLORS` (sky, green, yellow, coral, violet, amber, pink, teal). Colours never repeat inside a video and never clash with that video's background tone (`THEME_CLASHING_CUBES`). Older single-colour videos keep `CUBE_COLOR_ID`. The faces are lit (light top, base left, dark right) with dark edges. Cube height is 1.15 × tile height; the spacing and footing rules below are what actually prevent a stack further back from reading as a taller one in front.
- Levels escalate within every video (tiers 0, 0, 1, 2 for four rounds). Cube totals per tier:
  - Easy: 4–6, 5–8, 7–10.
  - Medium: 6–9, 8–11, 10–13.
  - Hard: 8–11, 10–13, 12–15.
  Consecutive rounds never repeat a total. Cubes are spread over mixed stacks:
  - no height repeats on more than half of the stacks, so 3 + 3 + 3 never happens;
  - boards with more than four stacks use at least three different heights;
  - there is at least one stack per 2.5 cubes (for example, 9 cubes as 2-2-4-1). Later tiers keep the most occluded readable layout out of several candidates.
- Hidden cubes always count: a stack's height includes cubes that other stacks hide.
- Spacing: stacks never stand directly beside, in front of, or behind each other. Only the screen-level diagonal neighbour is allowed. Otherwise a stack one cell behind another reads as a taller stack in front of it.
- Solvability is validated with an ID-buffer render:
  - every stack's top face is at least 60 % visible;
  - both side faces of the bottom cube are at least 60 % visible;
  - at least 75 % of sample points along the bottom cube's two floor edges are visible. Every stack's footing is therefore seen, so a stack standing further back never reads as a taller stack in front.
  - every cube shows at least 35 % of one side face.
- Each stack casts a contact shadow. During the count, a glowing footprint frames the base of each stack as it is counted.
- Round timeline:
  - 0.6 s: the cubes drop in.
  - Flash: Easy 2.5 s, Medium 2.0 s, Hard 0.3 s.
  - 0.3 s: the cubes dissolve.
  - 3.0 s: thinking, with a `?`, `How many cubes?`, and a numeric timer that ticks at 3, 2, and 1 seconds.
  - 0.4 s: the cubes return.
  - 1.3 s: stack-by-stack count, with a height label over each stack and a counting total.
  - 0.9 s: the green total is held with a burst.
- The hook intro (1.0 s) shows a fixed concept cluster (never the real first board), `COUNT THE CUBES.`, and `N LEVELS · X SECONDS TO LOOK`; the 3.0 s READY screen (`You will count the cubes.`) follows before the first level. The cover is the game's 3D cover template (see Per-video 3D covers).
- Manifests reuse `displayed_counts` for the per-round totals. Filenames: `PZ_XXXX_cube_count_<difficulty>`.

## Lucky Pick V3 — snake chase, Puzzly for You look

The current Lucky Pick ("Pick One"). One no-difficulty game per video: seven targets scatter in an open arena while a neon snake hunts them; the last one left wins. `lucky_pick.generate` builds it (`map_version: snake_chase_v1`); the simulation is `puzzly/puzzles/lucky_snake.py` and the frames are `puzzly/visuals/lucky_snake.py` (`draw_lucky_frame` dispatches to it). It shares the dark palette, numeric timer, header, progress row, and outro with the maze version below.

- Simulation: deterministic and seeded, run once at generation time at 120 Hz and recorded at 30 fps (`frames`: time, head x/y, heading, snake length, and every live target's position; `catches`: target, time, and position). Validation re-runs it from `map_seed` and `attempt` and must reproduce the same game.
  - Arena: a solid circle, centre (540, 1000), radius 440. No corners, so targets cannot be trapped.
  - Targets: seven random, well-spaced start positions (shuffled so no index is favoured). All seven use exactly the same rules, so no colour or position is advantaged: a smooth wander; within 280 px of the head they dodge like real prey, mostly side-stepping out of the snake's line of travel and partly moving away (pure running-away would push everyone to the rim); a steady pull back from the rim into open space; darting back into the open at an angle when cornered; fleeing the body; and keeping clear of each other so every colour stays readable. Max speed 250 px/s with inertia.
  - Snake: emerges from a den at the bottom of the rim when the pick window closes; the den then fades away (`den_opacity`). It never simply sweeps the targets in order around the arena: it prowls at 80 % speed toward random waypoints in the inner arena (at least 320 px away, so it cuts across), with a slow side-to-side sway; it strikes at full speed at a target that comes within 250 px inside a 75° cone in front of it; it gives up on prey that gets more than 400 px away after 1.2 s; after 3.2 s without a catch it hunts the nearest target; and a chase longer than 2.2 s makes it turn on another. Its turn rate is limited (3.4 rad/s prowling, 4.6 striking), so it sweeps in arcs and overshoots. Speed 195 px/s, +14 per catch, plus a boost when a chase stalls; length 230 px, +55 per catch. The head eats any target it reaches.
  - Acceptance: a chase of 9–20 s, the first catch after at least 1.6 s, catches at least 0.45 s apart, and a final duel (last two targets) of at least 1.2 s. Rejected attempts are re-rolled (usually 1–4).
- Look: a dark circular floor with a faint grid and a neon rim (violet at the top, cyan at the bottom). The snake has no face: a tapered light tube (dark edge, bright ice-white core, highlight, cyan bloom) with a brighter head bead. A swallowed target shrinks and spins into the head over a colour burst, travels down the body as a bulge, and stays as a band of its colour near the tail, so the body keeps score. Fleeing targets shiver and glow brighter when the head is close and leave fading afterimages when they move fast.
- Timeline: 1.0 s hook intro (the real targets in the empty arena under `PICK ONE.`), 0.25 s appearance, exactly 5.0 s selection (`PICK ONE.`, `ONLY ONE SURVIVES.`, numeric timer, ticks at 3, 2, 1; targets bob in place inside rings in their colour), the chase (`N LEFT`, red at three or fewer, over the progress row), then `SURVIVOR!` with zoom, glow, and two bursts during the 1.7 s hold, and the shared 3.6 s end card with the winner and `DID YOURS SURVIVE?`. Typical videos run 21–26 s.
- Rings mark the choices only while the viewer picks; they fade out over 0.3 s when the chase starts (`pick_ring_alpha`).
- Audio: a whoosh as the snake leaves its den, a bite (snap and pop, panned by position) on every catch, a warning pulse before the last two catches, then the ding and sparkle for the survivor.
- Cover: the 3D cover template; the card is the empty arena with the targets at their start positions as 3D tokens and a staged snake rising from its den in an S-curve, head pointing into open space at least 170 px from every target (`snake_board`, `cover_snake_pose`). It is never taken from the chase, so it gives no hint of which target is eaten first or who survives.

## Lucky Pick V2 — neon maze (earlier version)

`lucky_pick.generate_maze` (`map_version: neon_maze_v1`) and the maze half of `puzzly/visuals/lucky_pick.py`. It is no longer generated but stays valid, so saved maze videos can still be validated and re-rendered.

- Maze:
  - Every video builds its own maze from a stored `map_seed`: a Wilson spanning tree over a 5×6 node grid (x 150–930, y 430–1370), a portal entrance corridor at (540, 1515), and two shortcut loops between far-apart branches.
  - Dead ends are the target pockets. There are at least nine, spread over the top, bottom, left, and right, and the loops never touch a pocket. The character therefore never walks over a target it has not chosen.
  - Seven targets (one shared shape, seven neon colours) take seven far-apart pockets.
- Rendering: corridors are recessed dark channels (118 logical px wide, with an inner shadow and a dot grid) carved into hatched wall blocks. Every wall edge has a neon rim, violet at the top fading to cyan at the bottom, with bloom. Pockets have rings in their target's colour only while the viewer picks (hook intro and the 5.0 s selection); the rings fade out over 0.3 s when the pick window closes and never return (`ring_opacity`). The entrance is a spinning portal.
- Selection:
  - `PICK ONE.` and `ONLY ONE SURVIVES.`, with the numeric timer and ticks at 3, 2, and 1 seconds. The selection window is exactly 5.0 s after a 0.25 s appearance.
  - The creature stays hidden until it emerges from the portal.
- Creature ("the devourer", radius 64 logical px), designed for adults so the game never reads as a children's game: an armoured gunmetal sphere (lit from the upper left, red fresnel edge, crisp highlight, helmet seam) with four angled dorsal spikes, a red rim and a low red aura that swells before it strikes. One recessed visor eye glows red with a vertical slit pupil that looks where it moves; the visor narrows into a V-shaped glare when it is about to eat, and flickers briefly instead of blinking. The closed jaw is a jagged seam; the open jaw is a glowing maw lined with bone-coloured teeth. Never add cartoon eyes, cheeks, a tongue, or smiles. It glides with barely any squash and a slight lean into turns, and leaves a red trail.
- Movement: a constant 680 px/s cruise with a 0.16 s speed-up and slow-down, along the shortest route. A fading trail follows the creature. It stops 92 px short of each target.
- Eating (0.82 s):
  - 0.16 s anticipation: it crouches, frowns, and starts opening its mouth.
  - 0.36 s bite: it lunges, the mouth opens wide (teeth, glowing throat, tongue), and the target shivers, spins, and shrinks into the mouth. The jaws close at 70 % of the bite, with a colour-shard burst.
  - 0.30 s: it shudders with a satisfied squint while red light pulses from its jaw seam, then settles into the empty pocket.
- The header counts `N LEFT` (red at three or fewer) above a row of the seven targets, where eaten ones are struck out. The winner is never eaten. It gets `SURVIVOR!`, zoom, glow, and two bursts during the 1.7 s hold.
- The hook intro is 1.0 s: the real maze and targets under `PICK ONE.`. The cover is the game's 3D cover template (see Per-video 3D covers). The outro is the shared end card with the winning target in the ring and `DID YOURS SURVIVE?` (1.6 s when the maze version was made, 3.6 s now). Typical videos run 21–30 s.
- Fingerprints and manifests store the map version and seed, geometry, shape, colour-to-pocket mapping, winner, elimination order, and timeline. `corridor_template_id` in the manifest holds `neon_maze_v1:<map_seed>`.
- Older corridor-template manifests are still validated by the legacy rules (`_legacy_errors`).

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

- Legacy light theme used by games that have not yet been migrated to the Puzzly for You look: polished 2D, rounded geometry, bold outlines, subtle depth/shadows/highlights, bright semantic colors, and strong contrast. Puzzle Fit uses its own dark theme. Migrate other games to the dark adult look only when the user asks.
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

## Bounce Arena V2 — gravity physics, Puzzly for You look

Standalone, no difficulty. The physics are in `puzzly/puzzles/bounce_arena.py` (`version: 8`) and the frames are `draw_bounce_frame` in `puzzly/visuals/bounce_arena.py`.

- Physics: deterministic, with a fixed 1/240 s step.
  - Setup: six balls (radius 40 logical px) start near the centre of a ring (radius 400) centred at (540, 930).
  - Gravity is 980 px/s². Ball-to-ball collisions are perfectly elastic, so momentum and energy are conserved.
  - Wall bounces reflect the ball, and the spinning ring passes 12 % of its surface speed to the ball. The ring spins once every 7 s, in a seeded direction.
  - After each wall bounce, only the ball's speed is rescaled (never its direction) to keep its energy between 85 % and 145 % of the ring's inner height. This keeps the game lively without steering any ball.
  - The ring is a solid band (20 px thick) everywhere except the gap, with round caps at the gap edges (±0.29 rad).
  - Escape: a ball leaves only when its whole body fits between the caps; otherwise it bounces off the band or a cap. It never overlaps the band. Once fully clear of the ring, it is eliminated and flies on under gravity.
  - Stored data: 30 fps position frames, every impact (wall or ball, position, strength), and each exit's position and velocity.
- Acceptance: the seed sets only the initial conditions. Nothing preselects or steers an elimination or the winner. Rejected attempts retry with new initial conditions and are never forced. A simulation is accepted only if:
  - it ends naturally with one survivor within 9–21.8 s;
  - the first exit comes after at least 2 s.
- Look: dark background.
  - Ring: neon, fading from cyan opposite the gap to violet near it. The lips glow hot pink, and rotating tick marks show the spin.
  - Floor: a dark, radially lit arena floor.
  - Balls: glossy lit spheres with a lambert shade, a specular hotspot, and a crisp, slightly darker edge (no neon halo). They leave no trail.
  - Impacts: no visual effect at all (no sparks, flashes, or squash); hits are heard, not shown.
  - Exits: an exiting ball shows no burst at the gap; it flies a real ballistic arc behind the arena and lands in its order slot on the `OUT` shelf.
- Screens:
  - Selection (exactly 5.0 s): `PICK ONE.`, `LAST BALL IN THE RING WINS.`, and the numeric timer with ticks at 3, 2, and 1 seconds. The balls hover at their real start positions.
  - Play: an `N LEFT` header, red at two or fewer.
  - Win: the winner glides to the centre with zoom, glow, a crown, and bursts under `WINNER!` and `<COLOR> SURVIVES` during the 1.5 s hold.
  - Outro (3.7 s): the shared end card with the winning ball in the ring and `DID YOUR BALL WIN?`.
  - There is no separate intro; the cover is the game's 3D cover template (see Per-video 3D covers).
- Audio: impacts play a very quiet, low pentatonic "tock" (196–392 Hz, at most one every 0.08 s), with one pitch per ball, slightly louder for harder hits. Each exit plays a snap and a whoosh, and the win plays a ding and a sparkle.
- Total video length is at most 32 s (30 s of game and the 2 s longer end card). The fingerprint holds the full replay data.

## Matchstick Math V1 — move one match, Puzzly for You look

Standalone active type (Easy/Medium/Hard, always 3 levels, no challenge control). Generator `puzzly/puzzles/matchstick.py`, frames `puzzly/visuals/matchstick.py`, cover template `matchstick`. No dataset: puzzles are generated and checked exhaustively.

- Glyphs: digits are the seven segments of a digital clock (a top, b upper right, c lower right, d bottom, e lower left, f upper left, g middle) and never vary: 1 is the right-hand pair, 7 has three sticks, 6 and 9 keep their tails. `+` is a horizontal and a vertical stick, `-` one horizontal; `=` is fixed and never moves.
- A move takes one stick from any slot and puts it on any empty slot (same symbol or another). `moves(text)` tries every move and returns each true equation it can make. Valid results: `a ± b = c`, no leading zeros, non-negative result.
- A level is kept only when its false equation has exactly one true result (`len(moves) == 1`); the stored move is the first (fixed-order) move that makes it. Validation repeats the full search, checks the stored answer and move, the tier rules, and the thinking time.
- Levels (tiers 0, 1, 2), each harder: 1) single digits (`A ± B = C`); 2) one or two two-digit numbers, and the stick moves between two different symbols; 3) two-digit numbers on both sides, and the stick crosses the equals sign or changes the operator. Equations differ within a video. Generation takes about 0.03 s per video; the pool is tens of thousands of unique puzzles.
- Thinking grows per level (`MATCH_THINKING`): Hard 10/12/15 s, Medium 12/14/15 s, Easy 14/15/15 s. A level is 0.5 s entrance + thinking + 1.3 s move + 0.45 s answer + 1.0 s hold; `schedule` gives each level's start and `VideoSpec.round_duration` is the average (Hard video ≈ 49 s).
- Background: a procedural dark wood table (`puzzly/visuals/surfaces.py`, `table(size, theme, "wood", light)`: horizontal planks, long grain streaks, seams) tinted with the video's background tone and lit by a warm lamp over the card with a deep vignette, so the screen feels like a dim table rather than an empty gradient. Frame colour is a creator choice (UI `Çerçeve rengi`, `MATCH_FRAMES`: Turkuaz default, Amber, Lavanta, Mavi, Pembe, Limon, or Rastgele per seed), stored as `metadata["frame"]` outside the fingerprint: card outline, instruction pill, timer while time is plentiful (`_timer(accent=)`; it still turns warning/danger), hook subtitle, and the cover's pill. The end card keeps the shared look.
- Screen: `LEVEL n /3` and the numeric timer at the top; the large `MOVE 1 MATCH.` pill right above the equation card; `Make it true.` under it. Wooden matches are supersampled sprites with a calm look (`STYLE`): small muted-red heads, sticks at 80 % of their slot so heads do not cluster at the joints, no highlight stripe, and very faint empty-slot ghosts (drawn on their own layer). The first version's large bright heads at every joint made the digits tiring to focus on (user feedback). Reveal: the solving match glows, lifts, flies on an arc while turning to its new direction and settles; the card turns green and the true equation appears under it with a drawn check mark and a burst. Hook intro (1.0 s): `MOVE ONE MATCH.`, `3 LEVELS · EACH ONE HARDER`, and the real level-1 equation. Outro: the shared end card (`?/3`).
- Audio: ticks at 3, 2, 1, a whoosh as the match lifts, a snap as it lands, ding and sparkle. Music: tense, 92 BPM, E or A minor, woody kalimba taps (every game has its own lead voice).
- Cover: 3D template `MATCHSTICK` / `MATH` (amber gradient), `MOVE 1 MATCH.`, the real level-1 equation card, `MAKE IT TRUE.`, `3 LEVELS · EACH ONE HARDER`, floating 3D matches. Filenames `PZ_XXXX_matchstick_<difficulty>`. Comment prompts are in `YORUM.txt`.
- Tests: `tests/test_matchstick.py`.

## Cup Shuffle V1 — follow the ball under the cup

Standalone active type (the user's idea: "the ball under the cup, follow where it goes"). Produced only in Hard, always 3 levels with 3, 4 and 5 cups, shuffling more and faster each time. Generator `puzzly/puzzles/cup_shuffle.py`, frames `puzzly/visuals/cup_shuffle.py`, cover template `cup_shuffle`. The UI shows a locked `Hard` and no challenge control; filenames `PZ_XXXX_cup_shuffle_hard`.

- **Speed is tuned in one place** (the user will retune it after watching the videos): `CUP_LEVELS` in `puzzly/config.py`. Per level it holds `cups`, `swaps` (how many times two cups trade places), `swap_seconds` (how long one swap takes; smaller = faster) and `thinking`. Current values (after the user asked for 0.1 s faster swaps on every level): 3 cups / 6 swaps / 0.45 s, 4 / 9 / 0.32 s, 5 / 12 / 0.3 s, 4 s thinking (they were 0.55 / 0.42 / 0.32 s; the user then set level 3 back to 0.3 s because 0.22 s was too fast). Each made video stores its own `swap_seconds`, `thinking_seconds` and swaps in its round data, so retuning never changes existing videos, and their durations (`cup_round`, `cup_average_round`) come from the stored data. Validation accepts `CUP_SWAP_SECONDS_RANGE` (0.15–1.5 s).
- Level timeline (`phases`, all from config): 0.5 s the cups drop in; 0.45 s the ball's cup lifts (just far enough to show the ball, `LIFT_HEIGHTS`); 1.1 s it stays up; 0.45 s it comes down; the shuffle; the guess (numeric timer, ticks at 3, 2, 1); 0.55 s the right cup lifts and shows the ball; 0.5 s green burst; 1.0 s hold. A hard-mode video is about 39 s.
- Round data (`version: cups_v1`): cups, start position of the ball, `swaps` as `[a, b, front]` (position pairs with a < b; `front` is the one of the pair that travels in front of the other on its arc), speeds, and the cup colour (a different one every level). The answer is the ball's final position 1..N from the left, drawn uniformly per level before any swap is built (no position is favoured); the ball never ends where it started, the same pair never swaps twice in a row, and the ball's cup takes part in at least half of the swaps (at least 3). Validation replays the swaps to prove the answer. Generation takes about 0.5 ms per video.
- Look: a lamp-lit wood table (`surfaces.table`) with a felt mat in the video's background tone and a thin gold border; glossy 3D-shaded cups (cylindrical shading lit from the left, a highlight stripe, an embossed rib, a darker lip, a flat lighter top, an outline, all painted at 2x; colours follow the creator's object palette) with soft contact shadows; a gold glossy ball. Numbered badges 1..N under the positions let viewers comment a cup number. `LEVEL n /3`, `N CUPS`, the numeric timer during the guess, and a large pill: `WATCH THE BALL.` (drop-in to shuffle), `WHERE IS THE BALL?` (guess, plus `Comment the cup number ↓`), `IT WAS CUP n!` (reveal, green).
- A swap: the two cups trade places along arcs; the `front` cup passes lower on screen and a little bigger, the other higher and smaller (draw order by depth), so the motion never hints which cup holds the ball. The ball is drawn only while the viewer may see it (level start and the reveal), never during the shuffle or the guess (a test guards this).
- Hook (1.0 s): level 1's real cups with the ball showing under one of them, `FOLLOW THE BALL.`, `3 LEVELS · EACH ONE FASTER`, then the 3.0 s READY screen (`You will follow the ball.`). Outro: the shared end card (`?/3`).
- Cover: 3D template `CUP` / `SHUFFLE`, `FOLLOW THE BALL.`, the felt mat with the cups and the showing ball (cropped from the hook frame), `WHERE IS IT?`, `3 LEVELS · EACH ONE FASTER`, floating 3D cups and balls.
- Audio: a pop as every cup lands, a whoosh as the ball's cup lifts, a snap as it comes down, a soft pop for every swap (panned to the swap), ticks at 3, 2, 1, a whoosh, then ding and sparkle at the reveal. Music: tense, 100 BPM, D or E minor, its own `pizz` lead voice; the tension window spans the shuffle and the guess.
- Comment prompts are in `YORUM.txt`. Tests: `tests/test_cup_shuffle.py`.

## Mind Mix — one hard level each of Memory, Shade Spot and Puzzle Fit

The user's request: Puzzle Fit, Memory Challenge, and Shade Spot were the least watched videos, so they share one video, one level of each (the hard ones, "as if we were making level 3 of their own videos"), and the three games are paused as separate portal entries. The name, the cover, and the title cards between the games were left to the assistant: **Mind Mix** (`mind_mix`, filenames `PZ_XXXX_mind_mix_hard`). Generator `puzzly/puzzles/mind_mix.py` (data `version: mix_v1`; every section stores the game's own round data in `sub`, so the games' own generators and validators do the work), frames `puzzly/visuals/mind_mix.py`. The UI shows a locked `Hard` and no challenge or colour-similarity control.
- **Sections** (`MIX_GAMES`, always in this order): level 1 Memory Challenge's hardest level (the full 3×3 board, "where was it?", 9 shapes, memorize 5 s, 3 questions); level 2 Shade Spot's hardest level (a 5×5 pair, delta 0.04, 10 s); level 3 Puzzle Fit (three missing pieces, six tilted options, three traps) with a **shorter timer: 12 s** (`MIX_FIT_THINKING`; its own video thought for 20 s, which the user found too long). Nothing else of the games changes. Colour similarity is level 1 (distinct colours).
- **Title card before every game** (`MIX_SECTION_INTRO`, 1.8 s; the user's earlier worry was that viewers could not tell a game had started): `LEVEL n /3`, a large glossy icon of the game, the game's name on a pill (`MEMORY`, `SHADE SPOT`, `PUZZLE FIT`), one line saying what to do (`Remember the shapes.`, `Find the tile that changed.`, `Find the 3 missing pieces.`), and a `GET READY` bar that fills. The icons are fixed concepts (a 2×2 of numbered covers with one open card; a violet grid with one pink tile; one jigsaw piece), never a real level.
- **Timeline:** a 1.0 s hook (`MIND MIX.`, the three game cards, `3 GAMES · 3 LEVELS · 1 SCORE`), then three sections (card + the game: about 21.7, 15.1, 19.7 s), then the shared end card (`?/3`). A default video is about 61 s. Every section's length comes from its stored data (`mix_section_length`), `VideoSpec.round_duration` is the average, and `schedule(spec)` gives each start.
- **Rendering:** each section builds the game's own `VideoSpec` (`_sub_spec`) and calls that game's own drawing function (Memory's `draw_level`, Shade Spot's `draw_shade_round`, Puzzle Fit's `_frame`), so a game looks exactly as in its own video, with `LEVEL n /3` on Memory and Shade Spot and `3 MISSING PIECES` on Puzzle Fit; short fades join the sections. The creator's object palette never applies, the background tone does.
- **Cover:** the standard 3D template: `MIND` / `MIX`, `3 GAMES. 1 VIDEO.`, `CAN YOU DO ALL 3?`, `3 LEVELS · ONE SCORE`; the card holds the three game cards in a row (MEMORY, SHADE, FIT; fixed icons, so the cover never shows a real level); floating shapes and tiles from the video's own boards' colours.
- **Audio and music:** every game's own cue pattern, placed by the section timeline (`sound_cues`: a whoosh and a pop for every title card, card pops, ticks over the last 3 s, snap and ding on every answer, Puzzle Fit's whoosh and snap per piece, sparkles). Music: tense, 98 BPM, E or A minor, a new electric-piano voice (`rhodes`); windows per Memory memorize and question, and one each for Shade Spot and Puzzle Fit (`music_windows`).
- **Validation** (`mind_mix.errors` and the video checks): the game, level number, and intro length of each section, the game's own validator on its round (Puzzle Fit's with its timer range 6–30 s instead of the standalone value), Memory at its 3×3 `where` level, Shade Spot at 5×5, the order and numbering of the three, and the average round duration.
- Comment prompts for the description are in `YORUM.txt` (`MIND MIX`). Tests: `tests/test_mind_mix.py`.

## Laser Maze V1 — where does the beam end? (the user's request: another "trace it with your eyes" game; up to 5 levels, the creator picks the count)

Standalone active type, produced only in Hard (the UI shows a locked `Hard`), not in Mixed. Generator `puzzly/puzzles/laser_maze.py` (data `version: laser_v1`), frames `puzzly/visuals/laser_maze.py`, cover template `LASER` / `MAZE`. The `Challenges per video` box offers Auto (4), 3, 4, and 5, and the number of levels sets the difficulty: levels use tiers spread over the five (`LASER_TIER_SETS`: 3 levels use tiers 0, 2, 4; 4 use 0, 1, 3, 4; 5 use all), so the first level is always the easiest and the last always the hardest, and fewer levels mean steeper jumps. Six or more levels, or fewer than three, are rejected.

- Puzzle: a square board with two-sided 45° mirrors (`/` and `\`) in some cells, one laser entering through a port on the edge, and numbered receivers on other ports. Ports run clockwise from the top left (4n ports on an n×n board); receivers are numbered clockwise, and the answer is the number of the receiver the beam ends in. The beam always travels along cell middles and turns 90° at each mirror, so its path is deterministic and the answer unique by construction (`trace`; a beam always leaves the board, and tracing back from where it left returns it to where it entered). Receivers are at least two ports apart and never beside the laser's port. The correct receiver number is drawn uniformly per level before any board is built.
- **Difficulty is tuned in one place:** `LASER_TIERS` in `puzzly/config.py` (per tier the board size 5–9, the mirror share, the beam's bounces, the cells it visits, how many times it crosses its own path, the receivers 4/4/5/5/6, and the thinking time 6, 7, 8, 9, 10 s). A made video stores its own tier, rules, thinking, and trace seconds, so retuning never changes it. Beam length decides the trace time (`laser_trace_seconds`, 1.8–4.0 s); `laser_round(data)` and `VideoSpec.round_duration` (the average) come from stored data, and `schedule` gives each level's start. A level lasts 0.5 s entrance + thinking + trace + 1.3 s hold; a 4-level video is about 55 s with the 1.0 s hook and the 3.6 s end card.
- Screen: `LEVEL n /N` and the numeric timer at the top, a large `WHERE DOES IT END?` pill, a dark card holding the board (floor checker and grid, glossy mirrors drawn at 2x), the laser (a housing with a glowing lens) and the numbered receiver sockets around it, and `Comment the number ↓`. While thinking, only a short stub of beam leaves the emitter. Then the beam runs its whole path as a neon trail with bloom and a flash at every mirror, lands in the receiver (which turns green with a burst while the others dim), and the pill becomes `IT ENDS AT n!`. Hook (1.0 s): `FOLLOW THE LASER.`, `N LEVELS · EACH ONE TRICKIER`, and level 1's real board with the stub (never the path). Outro: the shared end card (`?/N`).
- Look: the video's background tone; the object palette does not apply (`NO_PALETTE_GAMES`): the beam is always red and the receivers teal.
- Cover: the 3D template `LASER` / `MAZE`, `FOLLOW THE LASER.`, level 1's board with the stub cut from the hook frame (`CROPS["laser_maze"]`), `WHERE DOES IT END?`, `N LEVELS · MORE MIRRORS EACH TIME`, floating numbered tiles.
- Audio: card pops, ticks at 3, 2, 1, a whoosh as the laser fires, a tick at every mirror (panned by position), a snap as the beam lands, then ding and sparkle. Music: tense, 106 BPM, A or E minor, a bent synth blip (`zap`) lead with its own motif.
- Validation (`laser_maze.errors`): board 5–9, mirrors in distinct cells, receivers distinct, clockwise, apart, and apart from the laser, the stored path, hits, and exit equal to a fresh trace, the answer the receiver the beam ends in, the stored bounces, cells, and crossings meeting the stored rules, timing ranges, and the tiers matching the number of levels.
- Filenames `PZ_XXXX_laser_maze_hard`. Comment prompts are in `YORUM.txt`. Tests: `tests/test_laser_maze.py`.

## Shade Spot V1 — find the changed tile, Puzzly for You look (paused: plays inside Mind Mix)

The user's idea after Memory Challenge seemed to underperform (they sent a screenshot of a spot-the-difference colour game): two stacked grids of nearly the same colours, and exactly one tile has a slightly different shade. Standalone and Mixed-eligible, produced only in Hard (the UI shows a locked `Hard`; filenames `PZ_XXXX_shade_spot_hard`). Memory Challenge stays; only the user decides whether it is replaced. Generator `puzzly/puzzles/shade_spot.py` (data `version: shade_v1`), frames `puzzly/visuals/shade_spot.py`, cover template `SHADE` / `SPOT`.
- **Puzzle:** each level draws a base palette of tile colours around one random hue (OKLab: lightness 0.50–0.78, chroma 0.085–0.17, hue within ±24°, every pair of tiles at least 0.022 apart). The top grid is the base; the bottom grid is identical except ONE tile moved `delta` away in OKLab (a random direction, mostly hue/saturation), so the answer is unique by construction. The odd colour must stay within its palette's range (a similar tile exists), so it never stands out inside its own grid. The answer is the tile's spot named like a chess square from the top left (`B3`: column letter, row number).
- **Levels** (`SHADE_LEVELS` in `config.py`, THE PLACE TO TUNE DIFFICULTY; the stored `delta`, `grid`, and `thinking_seconds` make validation and durations independent of later retuning): tier 0 3×3, delta 0.11, 5 s; tier 1 4×4, 0.08, 6 s; tier 2 4×4, 0.055, 8 s; tier 3 5×5, 0.04, 10 s (about 0.02 is the least an eye notices side by side). Default 4 levels use tiers 0–3 (`SHADE_TIERS`: 3 levels use 0, 2, 3; 5 levels use 0, 1, 2, 2, 3). A video's levels never get a smaller grid or a bigger difference, consecutive answers differ, and the spot is drawn uniformly. A level lasts 0.5 s entrance + thinking + 2.0 s reveal + 0.8 s hold; a default video is about 50 s with the 1.0 s hook, the 3.0 s READY screen, and the 3.6 s end card.
- **Screen:** `LEVEL n /N` and the numeric timer at the top, a large `SPOT THE DIFFERENCE.` pill right above two 540 px neutral cards (original above, changed below) with column letters (A–E) and row numbers, tiles in their exact colours on neutral dark cards so nothing tints a shade, and `Comment its spot, like B2 ↓` below (the example is never the answer). Reveal: the grids dim (only their area), the odd tile pair pops with a green outline in both grids, `FOUND IT.`, `IT'S B3` with a burst. Hook (1.0 s): `SPOT THE DIFFERENCE.`, `N LEVELS · EACH ONE HARDER`, and a fixed concept pair of violets (never a real level). Outro: the shared end card (`How many did you spot?`).
- **The creator's object palette never applies** (`NO_PALETTE_GAMES`): the colours are the puzzle. The background tone still applies.
- **READY screen** (the user's request: the hook showed a different, violet pair and the game then started at once, so viewers wondered whether it had started): after the 1.0 s hook, a 3.0 s READY screen like Cube Count's (`You will find the odd tile.`, `ARE YOU READY?`, a 3-2-1 countdown on the game's own background) prepares the viewer before the first board (`shade_spot` is in `READY_GAMES`). Videos made before it (`intro_duration` 1.0) keep the short hook and still validate.
- Cover: the standard 3D template `SHADE` / `SPOT` (unchanged layout), `SPOT THE DIFFERENCE.`, `WHICH TILE CHANGED?`; the card holds level 1's two grids SIDE BY SIDE and large (`cover_card`, the user's request: the stacked grids were tiny on the Instagram profile grid), glossy tiles with the colours livened up equally in both grids (`COVER_BOOST`), a small spoiler accepted like on the other covers; floating tiles in the level's colours.
- Audio: card pops, ticks at 3, 2, 1, a whoosh as the other tiles dim, a snap as the odd tiles pop, then ding and sparkle. Music: tense, 94 BPM, A or C minor, a celesta lead (new `celesta` voice) with its own motif.
- Tests: `tests/test_shade_spot.py` (validity and escalation over 60 seeds × 3 counts, exactly one differing tile at its stored delta, spot distribution, rejections, retuning safety, exact tile colours even with a creator palette, frames, cover, audio and music, UI).

## Chess: Mate in 1 V1

Standalone active type (not in Mixed). Generator `puzzly/puzzles/chess_mate.py`, frame `puzzly/visuals/chess_mate.py`, cover template `chess_mate` in `puzzly/covers.py`. Dependency: `python-chess` (pinned in `requirements.txt`).

- Positions are real Lichess puzzles from the Lichess open puzzle database (CC0), filtered once and stored offline in `assets/chess/mate_in_1.csv` (`CHESS_DATASET`); generation never touches the network. The filter keeps `mateIn1` puzzles whose position (after the opponent's first move) has exactly one mating move, which is the Lichess solution, with at least 500 plays and a popularity of at least 80. It keeps all 1600+ puzzles, the 5,000 most-played 1200–1599 ones, and the 3,000 most-played up to 1199 (source and filter in `assets/chess/SOURCE.txt`). Columns: id, fen, move (UCI), san, rating, popularity, plays.
- The UI replaces the Difficulty box with a `Min rating` number input (default 1800, 400–2400, step 50) and shows how many puzzles qualify (dataset: 3,220 at 1800+, 1,283 at 1900+, 400 at 2000+, 33 at 2200+; max 2412). `generate_spec(..., min_rating=)` draws from every puzzle rated at least that (`rating_pool`); the video's difficulty and filename suffix follow the chosen puzzle's band (`band_of`). Without `min_rating` (API/tests) difficulty picks the band: Easy ≤1199, Medium 1200–1599, Hard 1600+ (`RATING_BANDS`). The same puzzle is never produced twice (the puzzle id is in the fingerprint).
- Video: exactly 30.0 s (`CHESS_DURATION`), no intro, no outro, no effects and no animation: one still frame with `MATE IN 1`, a large `WHITE TO MOVE` / `BLACK TO MOVE` pill right above the board, the board seen from the side to move (lichess-style coordinates inside the edge squares), `One move. Checkmate.`, `Comment your move ↓`, the puzzle rating, and the static `Follow for more` pill.
- The answer is never shown in the video, cover, title, or description (it drives comments). It is stored only in the spec/manifest. After generation the UI shows it to the creator only, under each chess video (Draft and Final), as `Mat hamlesi: C6 > D5 (Bd5#)` (`chess_mate.move_label`; promotions add the piece).
- Pieces are the classic chess-diagram glyphs of the local Arial Unicode MS font (`ARIALUNI.TTF`), drawn like a diagram font: a white body under every piece, then the glyph in near-black on top, so black pieces show their own details (king's cross, queen's diamond, bishop's cross, rook bands) as crisp white lines and white pieces get a clean black outline. The user rejected the earlier Segoe UI Symbol drawings (black pieces looked smeared or lost their details); they remain only as the fallback when Arial Unicode MS is not installed. No downloaded piece artwork. Sprites are drawn at 4x and downsampled. Every piece is moved to the exact centre of its square by its drawn bounds (`_centered`; font glyphs sit on the baseline, which looked low).
- Background: a procedural felt cloth (`surfaces.table(..., "felt", ...)`) in the video's background tone under a warm lamp over the board, with a deep vignette. Still no effects or animation.
- Board colours are a creator choice (UI `Tahta rengi`, shown only for chess): `CHESS_BOARDS` in `config.py` (Klasik ahşap default, Turnuva yeşili, Buz mavisi, Lavanta, Mercan, Deniz yeşili, or Rastgele, resolved per video from the seed). Every dark square is a mid tone so both piece colours stay clear. It is stored as `metadata["board"]`, outside the fingerprint, and used by the frame and the cover.
- Comment prompts for the video description are in `YORUM.txt` (`CHESS: MATE IN 1`).
- Audio: no sound effects at all; the optional music (`Müzik: Açık`) is the only sound.
- Validation (python-chess): legal position, game not over, side to move matches, exactly one mating move equal to the stored answer, and the rating inside the difficulty band.
- Cover: the shared 3D template: `MATE` / `IN 1`, `WHITE TO MOVE.`, the real board on the tilted card, `FIND THE CHECKMATE.`, `ONE MOVE · COMMENT YOURS ↓`, and floating 3D pieces.
- Metadata credits the Lichess open puzzle database and the puzzle id. Filenames: `PZ_XXXX_chess_mate_<difficulty>`.
- Tests: `tests/test_chess_mate.py`.

## READY screen (Cube Count, Cup Shuffle, Memory Challenge, Flash Count — Shorts and long-form)

Games that show something for a moment get a 3.0 s READY screen right after the 1.0 s hook, so nobody misses the start: a small `GET READY`, what the viewer is about to do (`READY_TEXT`: `You will count the cubes.`, `You will follow the ball.`, `You will memorize 9 shapes.`, `You will read a number.`), a big pulsing `ARE YOU READY?` pill, and a 3-2-1 countdown ring (the number pops in, the ring drains each second, a tick sounds on every number, and a whoosh leads into the game). `puzzly/visuals/ready.py`; `READY_GAMES`, `READY_SECONDS`, `READY_INTRO_DURATION` (4.0 s) in `config.py` (`intro_outro` returns it, so `VideoSpec.total_duration` includes it). The game's own ground is used as the background where it has one (the cup table). Older videos and manifest-only records made before 2026-09-30 keep their 1.0 s / 2.0 s intros (`has_ready(spec)` is false for them) and validation accepts both. Tests: `tests/test_end_card.py`.

## YouTube long-form (16:9): Brain Test — all ten games in one video

The user's request: one 9–10 minute long-form that uses every game, so the channel's videos differ from each other and the viewer plays along with a score. The UI's long-form panel (`puzzly/ui/longform_panel.py`) starts with a `Uzun video türü` radio: `Brain Test` (default) or the older `Quick Math` pilot (kept, described in the next section). Engine `puzzly/braintest.py` (`VERSION braintest_v1`, history type `longform_brain_test`), thumbnail `puzzly/braintest_cover.py`. It reuses the pilot's 16:9 machinery (`longform._stage`, panels, `_edge_fade`, 2x cards) and every game's own Shorts renderer, timing, and audio (Hard only).

- Sequence (`SEQUENCE`, 13 segments in four blocks of 3, 3, 4, 3, `BLOCK_SIZES`): 1) Cup Shuffle, Puzzle Fit, Quick Math Shape Equations; 2) Cube Count, Matchstick Math, Chess Mate in 1 (medium band); 3) Memory Challenge, Puzzle Fit, Chess Mate in 1 (hard band), Quick Math Missing Signs; 4) Cube Count, Find the Exit, Line Follow. Quick Math always closes its block (it is the hardest to solve). Bounce Arena, Lucky Pick, Flash Count, and Missing Number are not part of it. Puzzles never repeat inside a video.
- Score: +1 for every correct level (`POINTS`: cup 3, fit 1, shapes 3, cube 4, match 3, chess 1, memory 3 (one per level, all questions right), signs 3, exit 4, line 5), 36 in all (blocks 7/8/8/13). Score checks (`checkpoint`, 5 s) close blocks 1–3; the `FINAL SCORE` card (11 s) adds the four blocks and shows rating bands (`WARMING UP`, `SHARP MIND`, `BRAIN MACHINE`, `UNSTOPPABLE`; no IQ or percentage claims). The video ends with the shared subscribe end card (6 s). Intro card 7 s.
- Cards: every game has a how-to card before it (5.5 s the first time, 3.5 s when it repeats): `GAME n / 13`, a 3D title, three steps, a preview of the game's real hook frame (never an answer), and a countdown panel (`STARTS IN` 3-2-1). Flash-type games (`GameDef.ready`: cup, cube, memory) show `ARE YOU READY?` with the countdown. The game's own READY screen is not used inside the long video (the card plays that role).
- In a game: the Shorts frame on a rounded stage (rows per `GameDef.rows`), a left panel (game, how to play, level and progress dots), a right `YOUR SCORE` sheet with the four blocks and a total (current block highlighted, `+1 POINT` toast when an answer lands), and `UP NEXT`.
- Chess (long version, `draw_chess_long`): 15 s of thinking (`CHESS_LONG_THINKING`), a 0.5 s entrance, then the answer: the from and to squares light up, a gold arrow, and the move in standard notation, 6 s (`CHESS_LONG_REVEAL`). The Shorts chess video still never shows the answer.
- Length: about 567 s (9:27) with the current timings (before the Cube Count formats and the three-level Memory it was 9:24); `estimated_duration()` computes it without building puzzles (the UI shows it). Chapter names: `1. Cup Shuffle` … `Quick Math: Shape Equations`, `Final Score`; each is at least 10 s.
- Episode number (`BRAIN TEST #n`): `episode_number(history)` counts saved Brain Tests in the SQLite history plus one. A Draft, a preview, or a failed render never uses a number, so an unsaved `#3` is `#3` again next time; a Final commit takes the next one. It is printed on the cover, in the intro, the title, and the `.txt`.
- Thumbnail (`render_braintest_thumbnail`, 1920×1080): every dimension steps with the episode so neighbouring uploads never look alike — one of six layouts (`LAYOUTS`; card left or right, second card behind, game chip strip, cropped big card), one of eight colour palettes (`PALETTES`: background tone, headline gradient, pill and sticker colours; it does not follow the video's own tone), the hero game (`BrainPlan.hero_key`, all ten in turn, using the video's real hook frame and never an answer), one of eight honest headlines, and a rotating challenge pill, plus the `#n BRAIN TEST` sticker. Consecutive episodes never repeat any of them. No IQ or "only 1%" claims; corners stay free for YouTube's overlays.
- Output and panel: same as the pilot (Final in `output/longform/PZ_XXXX_longform_brain_test.mp4` with `.jpg` and `.txt`; Draft in `data/longform_previews/`; `Bu videoyu Final olarak üret`; planning messages while puzzles are built, about 1–2 minutes because of Line Follow).
- Tests: `tests/test_braintest.py`.

## YouTube long-form (16:9): Quick Math brain test (pilot, kept as the alternative format)

The user also publishes long-form YouTube videos, besides Shorts and Reels. The UI's `Video formatı` radio switches between
`Shorts / Reels (9:16)` (everything above) and `YouTube uzun video (16:9)`, whose panel is `puzzly/ui/longform_panel.py`
(the app stops after it, so the Shorts controls are untouched). The engine is `puzzly/longform.py`; the thumbnail is
`puzzly/longform_cover.py`.

- Flow (about 9 minutes; the viewer always knows what to do, what comes next, and how to score):
  1. Hook intro (7 s): `TEST YOUR` / `MATH BRAIN`, `30 PUZZLES · 3 ROUNDS · 1 LUCKY BREAK`, the round chips, and "grab a pen and keep your score".
  2. Round 1, Shape Equations (10 puzzles). Round 2, Missing Signs (10). Each round opens with a how-to card (6.5 s: round n/3, a 3D title, three steps, `10 puzzles · +1 point each · pause anytime`, a preview of its first puzzle, and a `STARTS IN 3-2-1` pill) and closes with a score card (`ROUND n COMPLETE`, `How many did you get? __ / 10`, `Write it down`, `UP NEXT`).
  3. Lucky break: `LUCKY BREAK` card ("Now let's see how lucky you are", +1 bonus if your ball survives), one Bounce Arena game, then `DID YOUR BALL WIN?` with the winner.
  4. Round 3, the final round: the hardest levels (tiers 2 and 3) of both formats, alternating shapes and signs, easiest first.
  5. `FINAL SCORE`: `ROUND 1 + ROUND 2 + BONUS + ROUND 3 = ? / 31`, rating bands (0–10 warming up, 11–18 sharp mind, 19–25 math machine, 26–31 unstoppable; no IQ or genius claims), and "comment your score".
  6. End card: `THANKS FOR PLAYING`, a `SUBSCRIBE` button that a pointing hand taps (its fingertip on the + icon), "comment your final score", and the centred brand lockup. The intro ends with `ROUND 1 IS NEXT` (round 1's own card runs the countdown).
- Levels, timers, difficulty, hints, and the pause prompt are exactly the Shorts settings (Hard).
- In a game, the Shorts frame plays on a rounded stage in the middle of the 16:9 frame (portrait rows 95–1650).
  - Left panel: round n/3, the game name, how to play (three steps, fitted to the panel), `PUZZLE n / 10` with progress dots, and `Pause anytime`. In the lucky break it follows the game: `Pick your ball NOW` (pick window), `Is your ball still in?`, then `Did your ball win?`.
  - Right panel: a `YOUR SCORE` sheet with blank lines the viewer fills in (Round 1, Round 2, Lucky Break, Round 3, Total; the current row highlighted, finished rows ticked) and a green `RIGHT? +1 POINT` toast when each answer lands.
  - Below the right panel: `UP NEXT`.
- Games fade from and to the background over 0.3 s at both ends, and their audio slices get squared-sine fades (8 ms, or 0.35 s when music is on), so nothing hard-cuts or clicks against the cards.
- The whole video uses one background tone (`build_plan(background=...)`, random by default, drawn from its own generator so a background choice never changes the puzzles of a seed). Every sub-video carries it in its metadata, as does music (per game segment).
- Cards are drawn once at 2x (3D titles from `covers.text3d`) and then animated (zoom-in, fade-out, countdown). Audio concatenates each game's own Shorts audio with card stingers (pop, whoosh, countdown ticks, ding, sparkle).
- Rendering profiles (`longform.QUALITIES`): Draft 960×540 at 15 visual fps; Final 1920×1080 at 30 fps (CRF 18).
- Output:
  - Final: `output/longform/PZ_XXXX_longform_quick_math.mp4`, with a `.jpg` 16:9 thumbnail and a `.txt` holding the title, the description with chapters, and tags. It is committed to the SQLite history as `longform_quick_math`, and the same puzzle set is never produced twice.
  - Draft: a preview in `data/longform_previews/` (not in history). A failed or interrupted render deletes its partial files.
  - The panel shows the video, the thumbnail, download buttons for the video, thumbnail, and text, the title/description/tags, and the seed, background, and music. `Bu videoyu Final olarak üret` re-renders the shown Draft as Final with the same settings. The seed is also in the `.txt` and in the history's spec JSON.
  - Render progress never aborts on a page click: UI updates stop quietly and the render finishes.
  - Long-form records are hidden from the Shorts re-render list.
- Chapters: Intro, Round 1, Round 2, Lucky Break, Round 3, Final Score (every chapter at least 10 s long, as YouTube requires). The title is honest clickbait ("TEST YOUR MATH BRAIN 🧠 30 Puzzles, No Calculator | Can You Score 25+?").
- Tests: `tests/test_longform.py` and `tests/test_longform_cover.py`.

## Audio V7

### Background music (opt-in)

- The UI has a `Müzik` box (`Kapalı` by default, or `Açık`). When it is on, the app writes `metadata["music"] = "on"` into each spec. Metadata is not part of the fingerprint, so music never affects duplicate detection.
- Every Puzzly for You game plays music: the games with a 3D cover template (`music.supports_music`). Light-theme games render without it, and the UI says so.
- `puzzly/music.py` synthesizes the music locally (no copyrighted assets) and deterministically per video. The goal is a "challenge accepted" feel that never tires the ear. All games share one signature:
  - a soft pad under the whole video, with a thump at the start;
  - a bass and hat groove on one global beat grid from the first second to the end card, so it never restarts or stops between levels; it lifts slightly during thinking time;
  - a melody: every game has its own two-bar motif A and answer B, played A, B, A (the repeat ends one step higher) and then one bar of rest. Notes are chord tones, so the melody follows the progression. Every lead voice uses few, soft harmonics and click-free fades;
  - the last seconds of each timer (up to 3 s) swap the melody for an arpeggio and sixteenth-note hats on the same grid;
  - each answer adds a major chord on top;
  - a final chord plays under the end card, with a 0.4 s fade.
- Two moods: `fun` games (Lucky Pick, Bounce Arena) use major keys, bouncier motifs, and a soft clap on beats 2 and 4. `tense` games (all others) use minor keys and add a soft heartbeat (lub-dub) under the last seconds of every timer.
- Each game has its own character (`STYLES`), with keys chosen per video from the style's list:

  | Game | Mood | Character, lead voice | Progression | Tempo | Bass | Hats |
  |---|---|---|---|---|---|---|
  | Quick Math | tense | focused, ticking staccato pluck | i–VI–III–VII | 96 BPM | root | off-beat |
  | Puzzle Fit | tense | dreamy, long FM bell tones | i–iv–VI–v | 88 BPM | root | off-beat |
  | Find the Exit | tense | mysterious, dotted glass steps | i–VI–iv–V | 80 BPM | low, long | beats 2 and 4 |
  | Cube Count | tense | techy, syncopated square blips | i–VII–VI–VII | 104 BPM | octave | sixteenths |
  | Memory Challenge | tense | calm, music-box arpeggio | i–III–VII–iv | 84 BPM | root | off-beat |
  | Lucky Pick | fun | playful, bouncing marimba hook | I–V–vi–IV | 112 BPM | root–fifth | off-beat |
  | Bounce Arena | fun | energetic, octave-jumping synth riff | vi–IV–I–V | 120 BPM | eighth-note | off-beat |
  | Chess: Mate in 1 | tense | thoughtful, slow sparse piano phrases | i–III–VII–iv | 78 BPM | root | off-beat |
  | Cup Shuffle | tense | sneaky, staccato pizzicato | i–VII–iv–v | 100 BPM | root | off-beat |
  | Laser Maze | tense | sci-fi, bent synth blips | i–VI–III–VII | 106 BPM | root | off-beat |

  Memory's thinking windows are the memorize time and each question. Lucky Pick's and Bounce Arena's are the pick window, and their answer is the winner.
- The music peaks at about −19 dBFS and ducks 60 % under every sound effect, so ticks and dings stay clear. The final mix still goes through `finalize_mix`.
- Keep music off for videos that will use a trending in-app sound on YouTube.

Generate royalty-free effects locally: intro pop, object pop, soft timer pulse, answer ding, puzzle snap, sparkle, transition whoosh. Keep them clean, crisp, and game-like. No harsh buzzers or voices. Use float64 internally at 48 kHz, remove meaningful DC, apply an 8 ms smooth squared-sine fade at both SFX boundaries, keep individual peaks below −7 dBFS, and transparently scale overlapping mixes to at most −1 dBFS before integer PCM conversion. Never rely on hard clipping.

## UI and metadata

Streamlit fields: Puzzle Type (the active inventory above, including Flash Count, Lucky Pick, Hidden Motion Hunt, Cube Count, Chess: Mate in 1, and Mind Mix; the paused games are not offered), Theme when relevant, Difficulty, Operation, Challenges per video, Number of videos, Quality, Optional Seed. Lucky Pick has no difficulty or challenge control. Chess: Mate in 1 has a `Min rating` input instead of difficulty and no challenge control. Hidden Motion Hunt has no difficulty/challenge control and instead shows its required upload, Manual/Auto selector, and Manual editor. Difficulty defaults to Hard, because Puzzly for You videos are produced in Hard and multi-round videos escalate through levels inside one video; Easy and Medium stay selectable. Show dynamic duration, progress, elapsed time, output path, previews, and Windows output-folder button.

Bounce Arena is an active standalone puzzle type with no difficulty or challenge-count control; see its section below. It remains outside Mixed mode unless a later direct request enables it.

Metadata examples: `Solve the Shapes. No Calculator. 🔺🟦 #shorts`, `Can You Find All 5 Missing Numbers? 🔢 #shorts`, and `Which Piece Fits? 🧩 #shorts`. Puzzle Fit titles rotate between `Only One Piece Fits. Can You Find It? 🧩 #shorts`, `5 Levels. Each One Harder. 🧩 #shorts`, and `Which Piece Fits? Beat the Timer ⏱️🧩 #shorts`. Descriptions stay short, adult-facing, and challenge-oriented, and credit Puzzly for You. Never use IQ/genius claims or deceptive "only 1% can solve this" style claims. Manifests include sequence, matching cover filename, round count, and dynamic duration. Metadata CSV files are reports only and are never authoritative history.

## Publishing history, filenames, and covers

- Use Python `sqlite3` and `data/generation_history.sqlite`; no server or cloud database.
- The database is authoritative for fingerprint uniqueness and the global monotonically increasing sequence. Never derive a new sequence by scanning `output/`.
- Commit a fingerprint and sequence only after both video and cover render successfully. Database assignment is transactional; failures do not consume a fingerprint or sequence.
- New basenames use `PZ_{sequence:04d}_{puzzle_type_slug}_{difficulty_slug}`, for example `PZ_0024_memory_challenge_hard`. Keep lowercase ASCII-safe slugs and do not rename legacy files.
- Write a matching MP4 and JPG to the same output directory. Covers are rendered directly from a deterministic, clean puzzle hero state at Final 1080×1920 resolution, saved as JPEG quality 94, and are not decoded screenshots of MP4 files.
- Back up legacy `data/history.json` before one-time migration and retain it after verification.

## Validation and tests

Never render an invalid educational puzzle. Validate every video and round before export.

- Quick Math (Shape Equations): at least 300 Easy, 400 Medium, and 500 Hard specs covering one new shape per clue, correct clue results, the level ramp, order-of-operations traps on levels 3–4, distinct answers, manual round counts, determinism, and frame/cover rendering.
- Missing Number: at least 300 Easy, 400 Medium, and 500 Hard specs covering family distributions, valid answers/rules, readable value bounds, no within-video duplicates, and determinism.
- Puzzle Fit: at least 1,000 rounds covering coherent boards, Easy/Medium three-candidate stability, Hard nine-candidate single-edge near-miss layout, 5-second thinking on every difficulty, exactly one match, determinism, bounds, and no overlap.
- Multi-round: Auto defaults, explicit 3/4/5, computed durations, manifest round count, and unique video fingerprints.
- Layout: frame containment, visual center offset (normally ≤20 px), non-overlap, no clipped text/candidates, and separation of round indicator from content.
- Memory Challenge: generate at least 500 Easy, 500 Medium, and 700 Hard specs. Validate one 3×3 board, nine unique shapes/colours/positions, eight unique timed questions, the excluded final token, determinism, duration, fingerprints, dark-card lightness, and statistically ordered OKLab closeness. Validate shape bounds and the full reveal-state progression.
- Flash Count: validate the number rules, digit growth per level, difficulty-specific visible times (whole frames), unique numbers per video, determinism, fingerprints, and that the intro/cover never show a real number.
- Find the Exit: validate immediate inward passages for every exit, exact one-exit reachability, tree acyclicity, route correctness, deterministic generation, route length/turn/horizontal/downward movement thresholds, route branch competition, and increasing Easy/Medium/Hard complexity.
- Hidden Motion Hunt: validate required decodable upload, layout save/load, deterministic background hash/spec/fingerprint, Auto 7-object 2/2/3 tiers, Manual 1–20 objects and exact saved properties, supported shapes/colors, size/jump ranges, vertical-only motion, safe bounds, non-overlap/spacing, periodic loop state, exact 18-second duration, standalone Mixed exclusion, blank difficulty, filename, history, and manifest fields.
- Lucky Pick (snake chase): generate at least 140 specs. Validate determinism, the re-simulated chase, the acceptance window, one never-eaten survivor, a balanced winner index, targets inside the arena, eaten targets never returning, growth per catch, pick rings only during selection, frames, the cover, and metadata.
- Lucky Pick (earlier maze version): generate at least 700 specs. Validate seeded maze determinism, connectivity, dead-end pockets, one shared shape, seven distinct colours in unique pockets, routes along corridors that never cross another target, the speed profile, the eating state sequence (anticipation, wide bite, chomp, chew), the exact 5.0-second selection, the hidden creature during selection, winner survival and a uniform winner distribution, fingerprints, frames, the cover, manifests, and UI hiding.
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
