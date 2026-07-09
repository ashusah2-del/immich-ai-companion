# Templates reference

Every style/layout choice below is picked automatically per photo (usually by
a vision-language model looking at the photo, sometimes randomly) - nothing
here needs to be selected manually. This doc is just a reference for what's
actually available. Source of truth is always the code linked next to each
section; this file can drift, that can't.

## Collage layouts

Defined in [`app/collage.py`](app/collage.py), dispatched by `build_collage()`
based on how many photos are available (a random count between
`AIENH_COLLAGE_PHOTO_COUNT_MIN` and `AIENH_COLLAGE_PHOTO_COUNT_MAX`, default
3-10). Some layouts need an exact count; most scale to any count.

| Template | Photo count | Description |
|---|---|---|
| `grid_2x2` | 4 | Plain even 2×2 grid, equal-size squares. |
| `hero_duo` | 3 | One large "hero" photo, two smaller photos stacked beside it. |
| `filmstrip_3` | 3 | Horizontal strip of 3 frames on a dark background. |
| `mosaic_5` | 5 | One large hero photo + a 2×2 grid of 4 small tiles beside it. |
| `polaroid_scatter` | any | Photos scattered at random positions/angles across a grid of cells, like polaroids tossed on a table. |
| `washi_scrapbook` | any | Same scatter mechanic as `polaroid_scatter`, plus a colored washi-tape accent drawn across one corner of each photo. |
| `photo_booth_strip` | any | Classic vertical photo-booth print - photos stacked in one tall strip. |
| `circle_frame` | any | Photos cropped into circles, laid out in a clean row. |
| `retro_filmstrip` | any | Sepia-toned horizontal filmstrip bordered top and bottom by sprocket-hole bars, like a physical cut of 35mm film. |
| `two_photo_captioned` | 2 | Used for the "then and now" style and the cartoon-vs-original comparison - see below, it's its own mini-system. |

All templates use face-aware cropping (`_crop_to_face` in `app/collage.py`) -
photos zoom in on the recognized subject's face rather than a blind center
crop, so heads don't get cut off and faces aren't tiny.

### `two_photo_captioned` - three sub-layouts

Every call randomly picks one of three layouts (`app/collage.py`,
`_two_photo_side_by_side` / `_two_photo_stacked` / `_two_photo_diagonal`).
Captions overlay the photo itself behind a dark gradient scrim, positioned in
whichever margin (top or bottom) has the most clearance from the recognized
face (`_face_clear_band`) so text never covers it - except the diagonal
layout, which keeps captions off the photos entirely.

| Layout | Description |
|---|---|
| Side by side | Two photos left/right, each captioned on whichever edge (top/bottom) is farthest from the face. |
| Stacked | Two photos top/bottom instead of left/right, same face-aware caption placement. |
| Diagonal | Scrapbook-diary style: warm textured paper background, both photos get a white polaroid-style border and their own gentle rotation, cascading diagonally with a bold vertical date/label in the margin beside each one. |

Used by:
- **Collage worker's "then and now" style** - captions `"THEN · <year>"` /
  `"NOW · <year>"`, optionally with a vision-model-picked mood emoji
  (`filter_pipeline._build_then_and_now_photo`).
- **Cartoon worker's comparison collage** - captions `"Cartoon"` /
  `"Original"` (`cartoon_pipeline._build_comparison_collage`).

## Cartoon/character styles

Defined in [`app/cartoon_styles.py`](app/cartoon_styles.py). One is picked
per photo by a vision model (`ollama_client.select_best_character_style`),
which **excludes the N most recently used styles** first
(`db.get_recent_variants`) so it cycles through the whole list instead of
developing a favorite.

| Style | Description |
|---|---|
| `anime` | Japanese anime/manga style - expressive portraits, dynamic poses. |
| `cartoon_3d` | 3D Pixar/Disney-style animated cartoon - warm, family-friendly, whimsical. |
| `disney_2d` | Classic hand-drawn 2D Disney animated-film style - storybook, fairy-tale look. |
| `indian_superhero` | Desi comic-book superhero style - bold, culturally-rooted heroic look. |
| `superhero` | Western comic-book superhero transformation - action-movie-poster look. |
| `minecraft` | Minecraft video-game blocky voxel style - fun, playful, gamer-kid look. |
| `lego` | LEGO minifigure style - playful, blocky toy-like look. |
| `funko_pop` | Funko Pop vinyl bobblehead figure style - cute, big-head collectible toy look. |
| `figurine_3d` | Photorealistic 3D collectible action-figure material - the "3D printed figure" trend. |
| `claymation` | Stop-motion claymation style - warm, handcrafted, nostalgic look. |
| `retro_film` | Vintage 1950s Hollywood film-noir look with a physical filmstrip border. |

## Filter presets

Defined in [`app/filters.py`](app/filters.py). One is picked per photo by a
vision model (`ollama_client.select_best_filter`), Google Photos-style - no
forced rotation here since color grading is much more photo-dependent than
"which cartoon style," unlike the cartoon worker above.

| Preset | Description |
|---|---|
| `vivid` | Bright, punchy, highly saturated colors - landscapes, food, bold scenes. |
| `clarendon` | Bright punchy contrast with a cool-tinted highlight - Instagram's iconic look. |
| `teal_orange` | Cinematic movie-poster grade - teal shadows, warm orange skin/highlights. |
| `warm_golden` | Warm golden-hour tone - sunsets, outdoor portraits, cozy scenes. |
| `cozy_golden` | Warm golden-hour tone plus a soft glow - warm indoor/portrait shots. |
| `cool_blue` | Cool cinematic blue/teal tone - city, night, or overcast shots. |
| `bw_noir` | Classic dramatic black & white - portraits, moody or high-contrast shots. |
| `vintage_faded` | Faded retro film look with light grain - nostalgic or candid photos. |
| `matte_faded` | Flat matte look with lifted blacks and muted tone - everyday VSCO-style look. |
| `soft_glow` | Soft dreamy glow - flattering for portraits, kids, close-ups. |
| `pastel_dream` | Soft, light, low-contrast pastel look - dreamy and airy, bright/minimal scenes. |
