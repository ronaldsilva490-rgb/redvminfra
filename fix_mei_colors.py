#!/usr/bin/env python3
"""Fix MEI section colors in all models to ensure proper contrast."""
import re
import glob

# Define appropriate dark colors for each model's MEI section
model_colors = {
    'modelo-1-editorial.html': '#1a3d3d',      # deep teal (already correct)
    'modelo-2-esmeralda.html': '#047857',      # emerald
    'modelo-3-brutalist.html': '#1a1a1a',      # black
    'modelo-4-swiss.html': '#1d3557',          # blue (already correct)
    'modelo-5-pastel.html': '#6b6560',         # dark gray-brown
    'modelo-6-glass.html': '#6366f1',          # indigo (already correct)
    'modelo-7-retro.html': '#c25e3e',          # rust
    'modelo-8-luxury.html': '#c9a961',         # gold
    'modelo-9-tech.html': '#3b82f6',           # blue
    'modelo-10-minimal.html': '#1a1a1a',       # black
    'modelo-11-neumorphism.html': '#6c5ce7',   # purple
    'modelo-12-cyberpunk.html': '#ff006e',     # neon pink
    'modelo-13-bauhaus.html': '#1d3557',       # blue (already correct)
    'modelo-14-organic.html': '#6b7c5c',       # olive (already correct)
    'modelo-15-aurora.html': '#6f5fff',        # aurora purple
}

models = sorted(glob.glob('servicos/portal/modelos/empresarial/modelo-*.html'))

for model_path in models:
    model_name = model_path.split('\\')[-1]
    print(f'\nProcessing: {model_name}')

    with open(model_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content

    if model_name not in model_colors:
        print(f'  WARNING: No color defined for {model_name}')
        continue

    dark_color = model_colors[model_name]

    # Replace var(--accent-2) with concrete color in MEI section only
    mei_match = re.search(r'<!-- SEÇÃO MEI -->.*?</section>', content, re.DOTALL)
    if mei_match:
        mei_html = mei_match.group(0)

        # Replace background:var(--accent-2) with concrete color
        new_mei_html = mei_html.replace('background:var(--accent-2)', f'background:{dark_color}')

        # Also fix any var(--accent-3) references in stars to use a contrasting light color
        # For dark backgrounds, use white or light variant
        if dark_color in ['#1a1a1a', '#0a0a0f', '#07070d']:
            # Very dark - use white stars
            new_mei_html = re.sub(r'style="color:var\(--accent-3\);"', r'style="color:#ffffff;"', new_mei_html)
            new_mei_html = re.sub(r'style="color:var\(--accent-3\)"', r'style="color:#ffffff"', new_mei_html)
        else:
            # Use a light complementary color
            new_mei_html = re.sub(r'style="color:var\(--accent-3\);"', r'style="color:rgba(255,255,255,0.9);"', new_mei_html)
            new_mei_html = re.sub(r'style="color:var\(--accent-3\)"', r'style="color:rgba(255,255,255,0.9)"', new_mei_html)

        # Fix section-tag color
        new_mei_html = re.sub(r'style="color:var\(--accent-3\);">Para Autônomos',
                             r'style="color:rgba(255,255,255,0.8);">Para Autônomos', new_mei_html)

        content = content.replace(mei_html, new_mei_html)

    if content != original:
        with open(model_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'  FIXED: Using {dark_color} for MEI background')
    else:
        print('  OK - no changes needed')

print('\n=== Done ===')
