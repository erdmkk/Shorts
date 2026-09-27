# AGENTS.md — Puzzly Shorts Generator

## Mission

Build a completely local, deterministic, one-click generator for polished, language-free "Puzzly for You" YouTube Shorts for an adult audience. Videos should make adult viewers instantly think "challenge accepted": sleek, high-contrast, brain-teaser styling, a strong first-second hook, real tension, and a satisfying payoff. This is not a children's channel. It must run on Windows with CPU rendering and must not require paid APIs, cloud rendering, copyrighted assets, narration, subtitles, or manual video editing.

The current feature pass adds a persistent Manual Placement editor to standalone Hidden Motion Hunt while preserving all approved games, publishing, and rendering architecture. Line Follow is back, rebuilt as Weave V7 and produced only in Hard (see its section). Flash Count is now the number flash game (see its section).

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

Current active inventory: Quick Math, Missing Number, Puzzle Fit, Find the Exit, Memory Challenge, Flash Count, Lucky Pick, Hidden Motion Hunt, Cube Count, Bounce Arena, and Line Follow. (Removed at the user's request, do not re-add or re-suggest: a Cube Net game, "which cube does this net fold into?".)

Audience data so far: the brain games (Find the Exit, Quick Math, Puzzle Fit) get the most views and engagement, far more than chance games. New games should make viewers think hard, not rely on luck.

Protect existing puzzle games from unrelated changes. Adding or changing one requested game does not authorize redesigning or altering the gameplay of other games unless the user explicitly asks for those changes.

Line Follow was removed once after several redesigns ("it never turned out the way I wanted"), then the user asked for it to be fixed and brought back: it is active again (selector and Mixed pool) as Weave V7, produced only in Hard. Only the user decides whether it stays.

Odd One Out and Counting are deprecated. Their old files may remain if harmless, but they must not be reachable from the UI, mixed generation, metadata, documentation, defaults, or new samples.

Mixed batch generation selects its explicitly registered safe pool rather than every active type. Hidden Motion Hunt is standalone-only because it requires a user background. Bounce Arena is standalone-only in V1. Cube Count is a standard active type and may participate in Mixed mode.

## Product-scope instruction precedence

- The newest direct user instruction takes precedence when it conflicts with an older puzzle inventory, fixed game count, version label, or feature-scope statement in this file.
- An explicit request to implement a new puzzle type is sufficient authorization to add it and update the active inventory; do not pause for separate permission solely because the game is absent from an older list.
- Treat inventory and version-specific sections as descriptions of the current implementation, not permanent prohibitions on future explicitly requested work.
- This precedence applies to product scope. Continue to preserve project-wide architecture and safety rules unless the user explicitly requests a compatible architectural change.
- In particular, preserve SQLite generation history, duplicate prevention, filename conventions, disposable output-folder behavior, Draft/Final rendering profiles, the safe audio pipeline, direct cover generation, deterministic validation, and local/offline-first operation.
- Continue protecting unrelated existing games from incidental gameplay or visual changes.
- Line Follow is active (Weave V7, Hard only).

## Multi-round architecture and pacing

`VideoSpec` contains validated `rounds`, `intro_duration`, `outro_duration`, `round_duration`, and computed `total_duration`.

Auto defaults: Quick Math uses 4 levels (see its section). Missing Number and Puzzle Fit use 5 rounds. Missing Number uses 4.0 seconds thinking; Puzzle Fit uses 5.0 seconds for every difficulty (see its section for its own intro/outro timing). Find the Exit uses 4 rounds with Easy 5.0 and Medium 6.0 seconds thinking; Hard thinks 5, 6, 7, 8 (and 9) seconds on levels 1–4 (5). Flash Count uses 4 levels by default and supports manual 3/4/5. Memory Challenge and Lucky Pick each use one fixed game. Hidden Motion Hunt uses one continuous 18-second scene. Centralize timing and compute duration dynamically. Same seed/settings reproduce the content. Prevent duplicates.

## Shared visual timeline

- Intro: 1.0–1.5 seconds, concept-specific, energetic, and branded. Never show an EASY, MEDIUM, or HARD difficulty badge in intros or covers. Quick Math uses +, −, ×, ÷; Missing Number uses a short sequence with a missing slot; Puzzle Fit uses a coherent board/hole/options cue with puzzle-piece imagery and no unrelated X or primary question-mark cue.
- A small decorative dot indicator near the top shows round progress without words.
- Thinking uses a thin rounded progress bar that shrinks smoothly; never use a 5–4–3–2–1 countdown.
- Between rounds use a restrained 0.3–0.5 second scale/fade, card slide, or soft wipe.
- Outro: 0.7–1.0 seconds with brand mark, small bounce, and subtle sparkle; visually loop-compatible.
- Every game ends with the shared `draw_cta` "Follow for more" call to action: a solid rounded pill button with a clean Segoe UI Bold label (never the handwritten display font).
- No voice, spoken language, subtitles, written instructions, welcome, subscribe text, or negative failure cues.

## Per-video background tone (all dark-theme games)

Each Puzzly for You video uses one dark background tone from `DARK_THEMES` in `puzzly/config.py`: violet, ocean, teal, crimson, emerald, ember, or plum. The creator chooses it in the UI (`Arka plan rengi`); `Rastgele` (the default) keeps `dark_theme_for(puzzle_type, seed)`, random per video with equal odds. Either way it is never per round and identical for all of a video's frames and its cover (`palette.background_for`).

## Creator colour choices (all dark-theme games)

`puzzly/palette.py`. The UI offers two boxes next to each other: `Arka plan rengi` (Rastgele or one of the seven tones) and `Nesne paleti` (Klasik, Neon, Pastel, Mücevher tonları). The choices are stored in `VideoSpec.metadata` (`background`, `palette`), outside the fingerprint like music, and saved with the spec so a Final re-render matches; the defaults (`random`, `classic`) are not stored.
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

`draw_puzzle_fit_outro` in `puzzly/visuals/puzzle_fit.py` is the one end card for every Puzzly for You game (Puzzle Fit, Find the Exit Hard, Cube Count, Memory Challenge, Quick Math, Lucky Pick, and Bounce Arena). It is built for viewers who do not read. Keep text to one short line.
- A large glowing ring fills around the centre (0.1–0.7 s). Inside it is either:
  - the score `?/N` (`?` in the accent colour; N is the round count, or `total=`, such as 8 for Memory);
  - the winner itself, for pick games (`hero=`: the winning Lucky Pick target or Bounce Arena ball).
- One letter-spaced line: `COMMENT YOUR SCORE`, or the pick game's short question in capitals (`DID YOURS SURVIVE?`, `DID YOUR BALL WIN?`), with a bouncing chevron.
- A large `Follow for more` button with a `+` icon slides up. A finger glides in, taps the `+` icon (never covering the label), and the button presses, flashes, and sends a ripple.
- The brand stays small at the bottom: the mark plus `Puzzly for You`. Soft particles drift upward in the accent colour.
- Themes pass `palette=` and `background=` (for example Missing Operators uses its teal and amber theme).

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

## Puzzle Fit V10 — Puzzly for You pilot

Puzzle Fit is the pilot for the adult "challenge accepted" look. Its dedicated renderer lives in `puzzly/visuals/puzzle_fit.py`; the shared pastel system and the shared intro/outro/dot-indicator rules below do not apply to it.

- Dark theme from the centralized `PUZZLE_FIT_PALETTE`: deep navy gradient, soft violet glow behind the board, faint dot grid near the edges, vignette, dark board card, and a translucent candidate tray. Use the clean Segoe UI/Arial bold UI font, not the handwritten display font.
- Each round cuts one deterministic abstract artwork (`rings`, `stripes`, `lowpoly`, `waves`, `burst`, with a palette from `PUZZLE_FIT_ART_PALETTES`) into bevelled, dark-outlined jigsaw pieces. Every candidate shows the hole's own artwork, so only the shape identifies the answer. Every round in a video uses a different style.
- Hook intro (1.0 s): the first level's real board and candidates are visible from frame one under `ONLY ONE FITS.` and `N LEVELS · EACH ONE HARDER`. Never show the answer. The direct JPG cover is this hook state at `COVER_TIME`.
- Levels escalate within every video and are shown as `LEVEL n /N`. Easy/Medium go 2×2 → 2×3 → 3×3. Hard goes 2×3 → mixed → 3×3, and the final level always uses the enclosed centre hole with no flat edge. Early Easy levels use two-edge decoys; later levels use one-edge decoys.
- Every difficulty uses 5.0-second thinking (`PUZZLE_FIT_THINKING`). Easy/Medium: three candidates. Hard: no corner holes, and nine candidates in a centred 3×3 grid: the answer plus all eight single-edge variants, so every decoy differs from the answer by exactly one edge.
- Timer: a rounded bar below the level header plus a visible remaining-seconds number. It turns from accent to warning (≤50 %) to danger (≤25 %) and pulses in the final 1.5 seconds, with audio ticks at 3, 2, and 1 seconds. This numeric timer is an intentional Puzzle Fit exception to the shared no-countdown rule.
- All candidates float with the same amplitude, differing only in phase, so motion never hints at the answer. Show no correct-answer cue during thinking.
- Round timeline: 0.35 s entrance, thinking, 0.55 s elimination (wrong pieces shrink and drop out in a deterministic staggered order while the answer gains a success glow), a 0.45 s lift-and-fly into the hole, then a snap with a glow, a ring, and a particle burst, followed by a solved hold. Round = thinking + 2.2 s.
- Outro (1.6 s): the shared Puzzly for You end card (see below).
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

- Levels escalate inside every video. Level n always uses grid tier n: 8×10 (one sweep, three vertical runs) → 10×12 → 12×14 → 13×16 → 14×17 (two sweeps, five vertical runs) cells (columns × rows). Auto is 4 levels; 3 stop at 12×14 and 5 reach 14×17 (the 13×16 proportions, one step larger). Every level is a larger grid, so corridors get narrower and the answer route longer (about 32 → 50 → 70 → 82 → 92+ cells). The maze fills the logical box x 100–980, y 400–1400. The large tiers keep 5, 4, and 3 candidate mazes instead of 10 so generation stays fast, and keep trying past 8,000 attempts until at least one is found. The retired 9×11 tier stays valid (`LEGACY_HARD_LEVELS`) so saved records can be re-rendered.
- Thinking time grows with the level: 5, 6, 7, 8, 9 seconds for levels 1–5 (`EXIT_HARD_LEVEL_THINKING`), stored per round as `thinking_seconds` and validated against the grid tier. Levels therefore last different times: `visuals.find_the_exit.schedule` gives every level's start and duration (used by frames, effects, and music) and `VideoSpec.round_duration` is the average of the levels, so the total duration stays exact. Older rounds without `thinking_seconds` keep 8.0 seconds on every level.
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
- Answers come from shuffled blocks per exit count ([0, 1, 2] for three exits, [0, 1, 2, 3] for four), so every exit is correct as often as the others, and the answer is fixed before retries, so acceptance rates cannot bias it. Exit columns vary per round within left, centre, and right bands.
- Timing: per-level thinking (above), 1.6-second glowing route trace, 0.9-second hold (level = 0.35 + thinking + 2.5 s), a 1.0-second hook intro (`ONLY ONE EXIT IS OPEN.`), and a 1.6-second outro. Audio ticks at 3, 2, and 1 seconds, then a whoosh, a ding on arrival, and a sparkle.
- Look:
  - Walls are rendered as lit 3D bars: a blurred drop shadow, a vertical gradient body, a bright top-left rim, and a dark lower edge.
  - The floor is a faint checker, softly lit from the exits.
  - Exits are star/moon/sun (and diamond on four-exit levels) portals of equal brightness, so none stands out; the start is a pulsing teal orb.
  - The reveal draws a neon trail with bloom. On arrival, the wrong portals dim and the correct portal gets the ring-and-particle burst.
  - The cover is the game's 3D cover template (see Per-video 3D covers).

## Line Follow — Weave V7, a board full of long same-colour cables, Hard only (current)

The user found every earlier version too simple and its lines broken-looking (braid; Tangle V3 short Catmull-Rom lines; Tangle V4 wobbly 8 px random walks with gap-cut bridges). Weave V5 (tidy lines from every target to a row of sockets) was judged too empty: "fill the screen, the lines must be much longer and wander everywhere", and only the correct line may start at the bottom so the viewer never wonders where to begin. Weave V6 did that and was liked, but its level 5 was "a bit short for level 5": the figure's line must get longer level by level, at level 5 at least 1.5 times V6's (V6 drew about 3.6k–5.4k px there), the other lines must grow with it, and both must fill the board with no meaningless empty space. Do not bring any of the earlier versions back. Rules from the user: produced only in Hard, levels 1 to 5 get harder, even level 1 is not easy, the board is as full as possible, only the figure's line reaches the bottom, the lines get longer every level.

Generator `puzzly/puzzles/line_weave.py` (data `version: weave_v7`, called by `line_follow.generate`), frames `puzzly/visuals/line_follow.py`. The UI shows a locked `Hard`; any requested difficulty gives the same Hard video, and filenames end in `_hard`. Auto is 5 levels (3 and 4 are supported: 3 use tiers 0, 2, 4).
- Board: target portals across the top (star, moon, sun, diamond, ring, heart, triangle), one line each: 5 at levels 1–3 and 4 at levels 4–5 (the board only holds about 15–17k px of line under the readability rules, so the longest levels have fewer, longer lines). Only the figure's line (always the first line in the data, stored from the figure up to its target) reaches the bottom row, where the figure stands at a random x; every other line ends at a plain rounded loose end, at least 150 px from the figure and never below y 1400. The answer is never the target nearest above the figure.
- Lines are uniform cubic B-splines stored as control points (tripled ends, a vertical lead out of the figure and into the targets), sampled every 5 px. They are grown one at a time, control point by control point (`Grower`), always heading for the emptiest room they can find (`_pick_goal`: of 36 random spots 230–950 px away, at least 90 px inside the sides and bottom and 130 px under the top band, the one farthest from any line), so they reach the corners too. The figure's line is grown first, from the figure: it keeps the strip under its target free while it wanders, keeps one self-crossing in reserve, and once its length budget is used (or, if it runs out of room, once it has 90 % of it: `EARLY_HOME`) it climbs to a gate under its target and straight up the target's chimney. Then each other line grows down from its target and ends as soon as its tip is clear after its length (or after 70 % of it, `MIN_DECOY_SHARE`, if it runs out of room). Each new control point finalises a piece of curve that `Tracer` checks at once; a line backs up when stuck (each dead end in a row backs up twice as far), restarts, and a round takes the previous line off (`Board.pop`) when one cannot be placed. Lines only move down through the band under the targets (y < 540), and every target keeps a clear chimney under it.
- Readability rules (the same `Tracer` replays them in `validate`): two lines closer than 18 px must be crossing there (lines are 7.5 px wide, so a gap is always over 10 px); every crossing at least 36°; crossings at least 32 px apart; the same two lines never cross twice within 2.5 crossing windows; turning radius at least 30 px (in practice about 115 px); no line within 40 px of another line's end or of a target's chimney; self-crossings per line at most 5, 6, 8, 9, 12 for the figure's line and 2, 3, 3, 4, 5 for the others.
- Tiers: the figure's line budget 3400, 4300, 5200, 6000, 7000 px (drawn about 3.5k–4.7k at level 1 and 6.8k–7.6k at level 5; `validate` requires at least 90 % of the budget); the other lines 2.6k–3.2k up to 3.7k–4.5k (drawn about 2.2k–3.5k at level 1 and 2.7k–4.5k at level 5; `validate` requires at least 70 % of the tier's lower bound); the figure's line crosses other lines at least 14, 18, 22, 24, 27 times (typically 25–49) and every other line crosses it; board coverage (40 px cells below y 540 and away from the figure, with a line within 44 px) at least 70, 73, 76, 76, 78 % (typically 76–85 %). Thinking 7, 9, 11, 13, 15 s (`LINE_THINKING`); a level lasts 0.35 + thinking + 2.4 s trace + 0.9 s hold, so 5 levels run about 76 s. Weaving a 5-level video takes about 25–150 s (`generate` is cached per seed).
- Look: shared dark background, card, header, numeric timer, and end card. Cables are all the same colour: a 7.5 px light core with a 12.5 px dark casing and a soft bloom, drawn at twice the frame size and scaled down. At every crossing a coin flip per crossing decides which line is on top, and that line's piece is redrawn with its casing, so over and under read clearly without cutting gaps and no line is always underneath. The figure is a glowing teal head-and-shoulders pictogram. Reveal: a neon trail traces the figure's line up to its target, the other targets dim, and the correct one gets the ring-and-particle burst.
- Hook intro (1.0 s): level one's real board (no answer) under `WHERE DOES IT LEAD?` and `N LEVELS · EACH ONE HARDER`. Cover: the 3D template (`LINE` / `FOLLOW`, `FOLLOW THE LINE.`, `WHERE DOES IT END?`) with a board of its own woven from the video id (`COVER_TIER`), never one of the video's boards.
- Music: tense, 100 BPM, A or E minor, harp arpeggios. Older `tangle_v4` samples still validate (`line_tangle`) but can no longer be rendered; `weave_v5` and `weave_v6` records can no longer be validated or rendered.

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

## Memory Challenge V7 — 3×3 grid, Puzzly for You look

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
- The hook intro is 1.0 s (`REMEMBER ALL 9.` and `8 QUESTIONS · N SECONDS TO MEMORIZE`). It uses a fixed concept grid of numbered covers and three demo tokens, never the real board. The cover is the game's 3D cover template (see Per-video 3D covers). The outro is the shared 1.6 s end card with `?/8`.
- Store the nine shapes, colour ids and values, positions 1–9, the eight-question order, the final automatic position, the memorize seconds, the colour level, and the palette variant in the spec and manifest. They drive fingerprints and history.
- Earlier five-token (V6) manifests cannot be re-rendered with the grid renderer.

## Flash Count V10 — number flash, Puzzly for You look

The user replaced the old shape-counting Flash Count completely: a number flashes for a split second, the viewer has 3 s to recall it, then the number is shown. Same name (`flash_count`), same slot in the selector and the Mixed pool. Generator `puzzly/puzzles/flash_count.py` (data `format: number_flash`, `version: number_flash_v1`), frames `puzzly/visuals/flash_count.py`. Old token-counting (V9) records can no longer be rendered.
- Produced only in Hard (the user's rule): the generator always makes Hard videos whatever difficulty is passed, and the UI shows a locked `Hard`. The number stays on screen 0.2 s (6 frames at 30 fps), and 0.3 s (9 frames) on 6-digit levels (`FLASH_VISIBLE`, by digit count). Levels grow within every video by digits (`FLASH_DIGITS`): 4, 5, 6 digits on the opening, middle, and final tier (the Cube Count split: tiers 0, 0, 1, 2 for 4 levels; 0, 1, 2 for 3; 0, 0, 1, 2, 2 for 5).
- Numbers are read, not recognised: no leading zero, no repeated neighbours (55), no counting runs of three (345, 987), no digit more than twice, and never the same number twice in a video.
- Level timeline (every phase is a whole number of frames): 0.9 s GET READY (empty slots, one per digit, under pulsing focus brackets) → the number flashes (plain white digits in the slots, no animation) → straight to 3.0 s thinking (the user had the random-bar mask after the flash removed; do not bring it back) (`?` in every slot, numeric timer, `What was the number?`) → 1.0 s reveal (digits drop into their slots one by one, violet) → 0.9 s hold (all slots turn green, burst, `Did you get it?`). Every level lasts 6.1 s; a 0.2 s flash leaves a 0.1 s longer hold.
- Intro (2.0 s, `FLASH_INTRO`): an `ARE YOU READY?` screen with empty slots, pulsing brackets, and `N LEVELS · ONE BLINK EACH`; no timer and no number, then the first level starts. Cover: the 3D template (`FLASH` / `COUNT`, `READ IT IN A BLINK.`, `WHAT WAS THE NUMBER?`) with its own random 4-digit number (`cover_number`, seeded by the video id, never one of its levels) and random floating digit tiles, so nothing from the game is spoiled; no time on the cover. Outro: the shared score-question end card.
- Audio: a shutter click on the flash, a whoosh on the mask, clock ticks over the last 3 s, a pop per revealed digit, then ding and sparkle. Music: tense, 108 BPM, E or D minor, a vibraphone lead with its own motif.
## Cube Count V1 — Puzzly for You look

Active standard puzzle type (Easy/Medium/Hard, default 4 rounds, manual 3/4/5, part of Mixed mode). Generator `puzzly/puzzles/cube_count.py`, renderer `puzzly/visuals/cube_count.py`; shares Puzzle Fit's dark palette, hook intro, level header, numeric timer, and score-question outro.

- Big blocks (the user's addition, `version: 2` rounds): besides the one-cell towers, every level has exactly one big block (`size: 2`), a single box on a 2×2 footprint and one cube tall, with no inner edges, that counts as ONE cube (a hurried viewer counts four). It never carries cubes on top and keeps the same spacing from every tower (`spaced_stacks`). It needs room, so version 2 boards are one cell larger (`GRID_BIG`: 5×5 on Easy, 6×6 on Medium/Hard); the count reveal labels it `1`. Painter order uses `stack_order` (axis-separation first, then centre). Older rounds without `version` keep their 4×4 / 5×5 boards and still validate.
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
- The hook intro shows a fixed concept cluster (never the real first board), `COUNT THE CUBES.`, and `N LEVELS · X SECONDS TO LOOK`. The cover is the game's 3D cover template (see Per-video 3D covers).
- Manifests reuse `displayed_counts` for the per-round totals. Filenames: `PZ_XXXX_cube_count_<difficulty>`.

## Lucky Pick V3 — snake chase, Puzzly for You look

The current Lucky Pick ("Pick One"). One no-difficulty game per video: seven targets scatter in an open arena while a neon snake hunts them; the last one left wins. `lucky_pick.generate` builds it (`map_version: snake_chase_v1`); the simulation is `puzzly/puzzles/lucky_snake.py` and the frames are `puzzly/visuals/lucky_snake.py` (`draw_lucky_frame` dispatches to it). It shares the dark palette, numeric timer, header, progress row, and outro with the maze version below.

- Simulation: deterministic and seeded, run once at generation time at 120 Hz and recorded at 30 fps (`frames`: time, head x/y, heading, snake length, and every live target's position; `catches`: target, time, and position). Validation re-runs it from `map_seed` and `attempt` and must reproduce the same game.
  - Arena: a solid circle, centre (540, 1000), radius 440. No corners, so targets cannot be trapped.
  - Targets: seven random, well-spaced start positions (shuffled so no index is favoured). All seven use exactly the same rules, so no colour or position is advantaged: a smooth wander; within 280 px of the head they dodge like real prey, mostly side-stepping out of the snake's line of travel and partly moving away (pure running-away would push everyone to the rim); a steady pull back from the rim into open space; darting back into the open at an angle when cornered; fleeing the body; and keeping clear of each other so every colour stays readable. Max speed 250 px/s with inertia.
  - Snake: emerges from a den at the bottom of the rim when the pick window closes; the den then fades away (`den_opacity`). It never simply sweeps the targets in order around the arena: it prowls at 80 % speed toward random waypoints in the inner arena (at least 320 px away, so it cuts across), with a slow side-to-side sway; it strikes at full speed at a target that comes within 250 px inside a 75° cone in front of it; it gives up on prey that gets more than 400 px away after 1.2 s; after 3.2 s without a catch it hunts the nearest target; and a chase longer than 2.2 s makes it turn on another. Its turn rate is limited (3.4 rad/s prowling, 4.6 striking), so it sweeps in arcs and overshoots. Speed 195 px/s, +14 per catch, plus a boost when a chase stalls; length 230 px, +55 per catch. The head eats any target it reaches.
  - Acceptance: a chase of 9–20 s, the first catch after at least 1.6 s, catches at least 0.45 s apart, and a final duel (last two targets) of at least 1.2 s. Rejected attempts are re-rolled (usually 1–4).
- Look: a dark circular floor with a faint grid and a neon rim (violet at the top, cyan at the bottom). The snake has no face: a tapered light tube (dark edge, bright ice-white core, highlight, cyan bloom) with a brighter head bead. A swallowed target shrinks and spins into the head over a colour burst, travels down the body as a bulge, and stays as a band of its colour near the tail, so the body keeps score. Fleeing targets shiver and glow brighter when the head is close and leave fading afterimages when they move fast.
- Timeline: 1.0 s hook intro (the real targets in the empty arena under `PICK ONE.`), 0.25 s appearance, exactly 5.0 s selection (`PICK ONE.`, `ONLY ONE SURVIVES.`, numeric timer, ticks at 3, 2, 1; targets bob in place inside rings in their colour), the chase (`N LEFT`, red at three or fewer, over the progress row), then `SURVIVOR!` with zoom, glow, and two bursts during the 1.7 s hold, and the shared 1.6 s end card with the winner and `DID YOURS SURVIVE?`. Typical videos run 19–24 s.
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
- The hook intro is 1.0 s: the real maze and targets under `PICK ONE.`. The cover is the game's 3D cover template (see Per-video 3D covers). The outro is the 1.6 s shared end card with the winning target in the ring and `DID YOURS SURVIVE?`. Typical videos run 21–28 s.
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
  - Outro (1.7 s): the shared end card with the winning ball in the ring and `DID YOUR BALL WIN?`.
  - There is no separate intro; the cover is the game's 3D cover template (see Per-video 3D covers).
- Audio: impacts play a very quiet, low pentatonic "tock" (196–392 Hz, at most one every 0.08 s), with one pitch per ball, slightly louder for harder hits. Each exit plays a snap and a whoosh, and the win plays a ding and a sparkle.
- Total video length is at most 30 s. The fingerprint holds the full replay data.

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

  Memory's thinking windows are the memorize time and each question. Lucky Pick's and Bounce Arena's are the pick window, and their answer is the winner.
- The music peaks at about −19 dBFS and ducks 60 % under every sound effect, so ticks and dings stay clear. The final mix still goes through `finalize_mix`.
- Keep music off for videos that will use a trending in-app sound on YouTube.

Generate royalty-free effects locally: intro pop, object pop, soft timer pulse, answer ding, puzzle snap, sparkle, transition whoosh. Keep them clean, crisp, and game-like. No harsh buzzers or voices. Use float64 internally at 48 kHz, remove meaningful DC, apply an 8 ms smooth squared-sine fade at both SFX boundaries, keep individual peaks below −7 dBFS, and transparently scale overlapping mixes to at most −1 dBFS before integer PCM conversion. Never rely on hard clipping.

## UI and metadata

Streamlit fields: Puzzle Type (including Memory Challenge, Flash Count, Lucky Pick, Hidden Motion Hunt, and Cube Count; excluding experimental Line Follow), Theme when relevant, Difficulty, Operation, Challenges per video, Number of videos, Quality, Optional Seed. Lucky Pick has no difficulty or challenge control. Hidden Motion Hunt has no difficulty/challenge control and instead shows its required upload, Manual/Auto selector, and Manual editor. Difficulty defaults to Hard, because Puzzly for You videos are produced in Hard and multi-round videos escalate through levels inside one video; Easy and Medium stay selectable. Show dynamic duration, progress, elapsed time, output path, previews, and Windows output-folder button.

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
