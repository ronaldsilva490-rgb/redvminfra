#!/usr/bin/env python3
"""Fix all orphan href="#" links in empresarial models."""
import re
import glob

models = sorted(glob.glob('servicos/portal/modelos/empresarial/modelo-*.html'))

for model_path in models:
    print(f'Processing: {model_path}')

    with open(model_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content

    # Fix "Ver vantagens" links -> open respective modals
    content = re.sub(r'href="#" class="service-link">Ver vantagens</a>',
                     r'href="javascript:void(0)" onclick="openModal(\'modal-consultoria\')" class="service-link">Ver vantagens</a>',
                     content)

    # Fix nav CTA "Abrir empresa" -> #abra-empresa
    content = re.sub(r'href="#" class="btn btn-primary nav-cta-desktop">Abrir empresa',
                     r'href="#abra-empresa" class="btn btn-primary nav-cta-desktop">Abrir empresa',
                     content)

    # Fix footer/nav "Abrir empresa grátis" -> #abra-empresa
    content = re.sub(r'href="#" class="btn btn-primary">Abrir empresa grátis',
                     r'href="#abra-empresa" class="btn btn-primary">Abrir empresa grátis',
                     content)

    # Fix CTA "Solicitar proposta" -> WhatsApp
    content = re.sub(r'href="#" class="btn btn-primary">Solicitar proposta',
                     r'href="https://wa.me/5511981050614?text=Olá, gostaria de solicitar uma proposta" target="_blank" class="btn btn-primary">Solicitar proposta',
                     content)

    # Fix footer service links -> #servicos
    content = re.sub(r'<li><a href="#">Consultoria</a></li>',
                     r'<li><a href="#servicos">Consultoria</a></li>',
                     content)
    content = re.sub(r'<li><a href="#">Assessoria Mensal</a></li>',
                     r'<li><a href="#servicos">Assessoria Mensal</a></li>',
                     content)
    content = re.sub(r'<li><a href="#">Perícia Contábil</a></li>',
                     r'<li><a href="#servicos">Perícia Contábil</a></li>',
                     content)
    content = re.sub(r'<li><a href="#">Contabilidade MEI</a></li>',
                     r'<li><a href="#mei">Contabilidade MEI</a></li>',
                     content)
    content = re.sub(r'<li><a href="#">Legalização</a></li>',
                     r'<li><a href="#servicos">Legalização</a></li>',
                     content)
    content = re.sub(r'<li><a href="#">BPO Financeiro</a></li>',
                     r'<li><a href="#servicos">BPO Financeiro</a></li>',
                     content)
    content = re.sub(r'<li><a href="#">Contabilidade Fiscal</a></li>',
                     r'<li><a href="#servicos">Contabilidade Fiscal</a></li>',
                     content)
    content = re.sub(r'<li><a href="#">Departamento Pessoal</a></li>',
                     r'<li><a href="#servicos">Departamento Pessoal</a></li>',
                     content)

    # Fix contact links
    content = re.sub(r'<li><a href="#">\(11\) 9999-9999</a></li>',
                     r'<li><a href="https://wa.me/5511981050614">(11) 98105-0614</a></li>',
                     content)
    content = re.sub(r'<li><a href="#">contato@totalempresarial\.com</a></li>',
                     r'<li><a href="mailto:contato@totalempresarial.com">contato@totalempresarial.com</a></li>',
                     content)
    content = re.sub(r'<li><a href="#">São Paulo, SP</a></li>',
                     r'<li><a href="#contato">São Paulo, SP</a></li>',
                     content)

    if content != original:
        with open(model_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print('  Fixed!')
    else:
        print('  No changes needed')

print('\nDone!')
