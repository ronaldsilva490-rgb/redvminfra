#!/usr/bin/env python3
"""Fix contrast issues in all empresarial models - ensure text is readable on backgrounds."""
import re
import glob

models = sorted(glob.glob('servicos/portal/modelos/empresarial/modelo-*.html'))

for model_path in models:
    print(f'\nChecking: {model_path}')

    with open(model_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content

    # Extract :root colors to understand the palette
    root_match = re.search(r':root\s*\{([^}]+)\}', content)
    if not root_match:
        print('  WARNING: No :root found')
        continue

    root_vars = root_match.group(1)

    # Check if model has light or dark accent-2
    accent2_match = re.search(r'--accent-2:\s*(#[0-9a-fA-F]{6})', root_vars)
    bg_match = re.search(r'--bg:\s*(#[0-9a-fA-F]{6})', root_vars)
    ink_match = re.search(r'--ink:\s*(#[0-9a-fA-F]{6})', root_vars)

    if not accent2_match or not bg_match or not ink_match:
        print('  WARNING: Missing color variables')
        continue

    accent2 = accent2_match.group(1).lower()
    bg = bg_match.group(1).lower()
    ink = ink_match.group(1).lower()

    # Determine if accent-2 is light or dark
    def is_dark_color(hex_color):
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return luminance < 0.5

    accent2_is_dark = is_dark_color(accent2)
    bg_is_dark = is_dark_color(bg)
    ink_is_dark = is_dark_color(ink)

    print(f'  Colors: accent-2={accent2} ({"dark" if accent2_is_dark else "light"}), bg={bg}, ink={ink}')

    # Fix MEI section based on accent-2 darkness
    if accent2_is_dark:
        # Dark background -> white text is correct
        mei_section = re.search(r'<!-- SEÇÃO MEI -->.*?</section>', content, re.DOTALL)
        if mei_section:
            mei_html = mei_section.group(0)
            # Ensure text is white/light
            if 'color:white;' not in mei_html and 'color: var(--bg)' not in mei_html:
                print('  FIXING: MEI section needs light text on dark background')
                # Add color:white to section
                mei_html = re.sub(r'<section id="mei"', r'<section id="mei" style="color:white;"', mei_html)
                content = content.replace(mei_section.group(0), mei_html)
    else:
        # Light background -> dark text needed
        mei_section = re.search(r'<!-- SEÇÃO MEI -->.*?</section>', content, re.DOTALL)
        if mei_section:
            mei_html = mei_section.group(0)
            # Replace white text with dark text
            if 'color:white;' in mei_html or 'color: var(--bg)' in mei_html:
                print('  FIXING: MEI section has white text on light background!')
                # Use ink color instead of white
                mei_html = mei_html.replace('color:white;', f'color:{ink};')
                mei_html = mei_html.replace('color: var(--bg);', f'color:{ink};')
                mei_html = mei_html.replace('color:rgba(255,255,255,0.8);', f'color:{ink}; opacity:0.8;')
                # Fix stars color
                mei_html = re.sub(r'style="color:var\(--accent-3\);"', f'style="color:{accent2};"', mei_html)
                # Fix button styles
                mei_html = re.sub(r'style="border-color:white;color:white;', f'style="border-color:{ink};color:{ink};', mei_html)
                content = content.replace(mei_section.group(0), mei_html)

    # Fix abra-empresa section - should always have dark text on light background
    abra_section = re.search(r'<!-- SEÇÃO ABRIR EMPRESA -->.*?</section>', content, re.DOTALL)
    if abra_section:
        abra_html = abra_section.group(0)
        # Check if background is light
        bg_match_section = re.search(r'background:var\(--([^)]+)\)', abra_html)
        if bg_match_section:
            bg_var = bg_match_section.group(1)
            # Extract that variable's value
            var_match = re.search(rf'--{bg_var}:\s*(#[0-9a-fA-F]{{6}})', root_vars)
            if var_match:
                section_bg = var_match.group(1).lower()
                if not is_dark_color(section_bg):
                    # Light background - ensure text is dark
                    if 'color:white' in abra_html or 'color: var(--bg)' in abra_html:
                        print('  FIXING: abra-empresa has light text on light background!')
                        abra_html = abra_html.replace('color:white;', f'color:{ink};')
                        abra_html = abra_html.replace('color: var(--bg);', f'color:{ink};')
                        content = content.replace(abra_section.group(0), abra_html)

    if content != original:
        with open(model_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print('  FIXED!')
    else:
        print('  OK - no fixes needed')

print('\n=== Done ===')
