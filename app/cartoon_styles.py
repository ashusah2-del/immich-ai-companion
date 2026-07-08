"""Named character-transformation styles for the cartoon worker. Ollama picks the
best-fitting style per photo (app.ollama_client.select_best_character_style), the
same selection pattern as app.filters.FILTER_PRESETS, instead of every photo always
getting the same generic cartoonization.

Each style's "style_prompt" is the base SDXL descriptive text app.ollama_client.
compose_character_prompt() builds on top of, tailoring it to the specific photo
(background, pose) the way compose_cartoon_prompt used to do for cartoon alone.
Phrasing patterns (voxel/no-anti-aliasing for Minecraft, bold-ink/cinematic-lighting
for superhero) are based on documented prompt conventions for each style, not guessed.
"""

STYLE_PRESETS = {
    "cartoon_3d": {
        "description": "3D Pixar/Disney-style animated cartoon - good for a warm, family-friendly whimsical look.",
        "style_prompt": (
            "3D Pixar/Disney-style animated cartoon character, big expressive eyes, "
            "smooth stylized features, vibrant saturated colors, soft cinematic "
            "lighting, animated movie still, high quality render"
        ),
    },
    "anime": {
        "description": "Japanese anime/manga style - good for expressive portraits and dynamic poses.",
        "style_prompt": (
            "Japanese anime/manga style character, large expressive anime eyes, "
            "cel-shaded coloring, clean crisp line art, vibrant anime color "
            "palette, detailed anime background art"
        ),
    },
    "disney_2d": {
        "description": (
            "Classic hand-drawn 2D Disney animated-film style - good for a warm, "
            "storybook, fairy-tale look distinct from the 3D Pixar look."
        ),
        "style_prompt": (
            "classic hand-drawn 2D Disney animated film character, traditional "
            "cel animation linework, large expressive eyes, warm painterly "
            "watercolor-and-gouache background art like a golden-age Disney "
            "feature film, soft romantic lighting, storybook fairy-tale quality"
        ),
    },
    "indian_superhero": {
        "description": (
            "Desi comic-book superhero style inspired by Indian superhero comics "
            "(Raj Comics/Amar Chitra Katha-style heroism) - good for a bold, "
            "culturally-rooted heroic look."
        ),
        "style_prompt": (
            "Indian comic-book superhero character in the style of classic desi "
            "superhero comics, dynamic heroic action pose, costume blending "
            "traditional Indian textile patterns and colors (saffron, deep red, "
            "royal blue, gold) with a modern superhero silhouette, ornate "
            "mythology-inspired armor accents, bold comic-book ink outlines, "
            "dramatic cinematic lighting, vibrant saturated colors, movie "
            "poster quality, 8K high detail"
        ),
    },
    "minecraft": {
        "description": "Minecraft video-game blocky voxel style - good for a fun, playful, gamer-kid look.",
        "style_prompt": (
            "Minecraft video game style character, blocky cubic head and body made "
            "of voxels, sharp pixel edges, no anti-aliasing, square eyes, simple "
            "blocky mouth and nose, standing in a Minecraft biome (grass blocks, "
            "trees, mountains), holding a signature Minecraft item (diamond sword, "
            "torch, or pickaxe), high-quality Minecraft game screenshot with "
            "cinematic lighting and a voxel world environment"
        ),
    },
    "superhero": {
        "description": "Comic-book superhero transformation - good for a bold, heroic, action-movie-poster look.",
        "style_prompt": (
            "comic book superhero character, dynamic heroic action pose, colorful "
            "superhero costume with cape and emblem, bold comic-book ink outlines, "
            "halftone shading, dramatic cinematic lighting, vibrant saturated "
            "colors, movie poster quality, 8K high detail"
        ),
    },
    "lego": {
        "description": "LEGO minifigure style - good for a playful, blocky toy-like look.",
        "style_prompt": (
            "LEGO minifigure character, cylindrical yellow-toned head with simple "
            "printed facial features, blocky plastic-textured body and articulated "
            "limbs, glossy plastic minifigure look, standing in a LEGO brick-built "
            "environment, studio product-photo lighting"
        ),
    },
    "claymation": {
        "description": "Stop-motion claymation style - good for a warm, handcrafted, nostalgic look.",
        "style_prompt": (
            "stop-motion claymation character, textured clay/plasticine look with "
            "visible fingerprint and sculpting-tool marks, warm handcrafted "
            "stop-motion animation style like classic claymation films, soft "
            "practical studio lighting, miniature set background"
        ),
    },
    "figurine_3d": {
        "description": (
            "Photorealistic 3D collectible action-figure material - the viral "
            "'3D printed figure' trend, good for a fun novelty keepsake look."
        ),
        # An earlier version tried to force a "figure inside a blister-pack box on a
        # desk" composition; verified live that img2img can't restructure the scene
        # that much without losing the subject entirely (low denoise just repaints
        # the same photo, high denoise produces an incoherent crowd scene). This
        # keeps the subject's real pose/scene (like the styles that work) and only
        # changes the material to a glossy toy-sculpt finish - verified live it
        # reads as a genuine collectible figure.
        "style_prompt": (
            "hyper-realistic 3D collectible action figure material, professional "
            "toy sculpt with fine detail, glossy plastic/resin skin and clothing "
            "texture with visible seam lines at joints, small circular display "
            "base beneath the feet, studio product photography lighting, "
            "photorealistic render, 8K detail"
        ),
    },
    "funko_pop": {
        "description": "Funko Pop vinyl bobblehead figure style - good for a cute, big-head collectible toy look.",
        "style_prompt": (
            "Funko Pop vinyl figure style, oversized rounded head with simplified "
            "black dot eyes, small chibi-proportioned body, glossy vinyl toy "
            "texture, small collectible-figure display base beneath the feet, "
            "studio product photography lighting"
        ),
    },
    "retro_film": {
        "description": "Vintage 1950s Hollywood film-noir cinema look with a classic filmstrip border - good for a dramatic, nostalgic old-movie look.",
        "style_prompt": (
            "vintage 1950s Hollywood film noir cinema still, dramatic high-contrast "
            "black-and-white or warm sepia-toned lighting, classic old-movie star "
            "styling and wardrobe, visible film grain, subtle scratches and dust, "
            "cinematic vignette, framed like a still from an old 35mm movie reel"
        ),
        # A literal sprocket-hole filmstrip border is precise graphic detail diffusion
        # prompting can't reliably render - drawn deterministically instead (app.frames).
        "post_process": "filmstrip_border",
    },
}
