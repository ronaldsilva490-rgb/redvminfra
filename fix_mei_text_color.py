#!/usr/bin/env python3
"""Fix MEI section text color for models with light/medium backgrounds."""
import re
import glob

# Models with light/medium backgrounds that need DARK text instead of white
light_bg_models = {
    'modelo-5-pastel.html': '#6b6560',      # gray-brown - medium, needs dark text
    'modelo-7-retro.html': '#c25e3e',       # rust - medium, needs dark text
    'modelo-8-luxury.html': '#c9a961',      # gold - light-medium, needs dark text
}

models = sorted(glob.glob('servicos/portal/modelos/empresarial/modelo-*.html'))

for model_path in models:
    model_name = model_path.split('\\')[-1]

    if model_name not in light_bg_models:
        continue

    print(f'\nFixing: {model_name}')

    with open(model_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content

    bg_color = light_bg_models[model_name]

    # Get the ink/dark color from :root
    root_match = re.search(r':root\s*\{([^}]+)\}', content)
    if not root_match:
        print('  WARNING: No :root found')
        continue

    root_vars = root_match.group(1)

    # Try to find ink or text color
    ink_match = re.search(r'--ink:\s*(#[0-9a-fA-F]{6})', root_vars)
    text_match = re.search(r'--text:\s*(#[0-9a-fA-F]{6})', root_vars)
    black_match = re.search(r'--black:\s*(#[0-9a-fA-F]{6})', root_vars)

    dark_color = ink_match.group(1) if ink_match else (text_match.group(1) if text_match else (black_match.group(1) if black_match else '#1a1a1a'))

    # Find MEI section
    mei_match = re.search(r'<!-- SEÇÃO MEI -->.*?</section>', content, re.DOTALL)
    if mei_match:
        mei_html = mei_match.group(0)

        # Replace white text with dark text
        mei_html = mei_html.replace('color:white;', f'color:{dark_color};')
        mei_html = mei_html.replace('color: var(--bg);', f'color:{dark_color};')
        mei_html = re.sub(r'color:rgba\(255,255,255,0\.8\);', f'color:{dark_color}; opacity:0.8;', mei_html)
        mei_html = re.sub(r'color:rgba\(255,255,255,0\.9\);', f'color:{dark_color}; opacity:0.9;', mei_html)

        # Fix stars - use accent color or darker variant
        mei_html = re.sub(r'style="color:#ffffff;"', f'style="color:{bg_color};"', mei_html)
        mei_html = re.sub(r'style="color:rgba\(255,255,255,0\.9\);"', f'style="color:{bg_color};"', mei_html)

        # Fix section tag
        mei_html = re.sub(r'style="color:rgba\(255,255,255,0\.8\);">Para Autônomos',
                         f'style="color:{dark_color}; opacity:0.7;">Para Autônomos', mei_html)

        # Fix button outline style
        mei_html = re.sub(r'style="border-color:white;color:white;',
                         f'style="border-color:{dark_color};color:{dark_color};', mei_html)

        content = content.replace(mei_html, mei_html)

    if content != original:
        with open(model_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'  FIXED: Using {dark_color} text on {bg_color} background')
    else:
        print('  OK - no changes needed')

print('\n=== Done ===')
