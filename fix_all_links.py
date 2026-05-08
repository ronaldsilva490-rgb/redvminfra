#!/usr/bin/env python3
"""Comprehensive fix for all orphan href="#" links in empresarial models."""
import re
import glob

models = sorted(glob.glob('servicos/portal/modelos/empresarial/modelo-*.html'))

for model_path in models:
    print(f'Processing: {model_path}')

    with open(model_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content

    # === NAV CTA BUTTONS ===
    # "Abrir Empresa" / "Abra sua Empresa" nav buttons -> #abra-empresa
    content = re.sub(r'href="#" class="btn btn-primary nav-cta(?:-desktop)?">Abrir Empresa',
                     r'href="#abra-empresa" class="btn btn-primary nav-cta">Abrir Empresa',
                     content)
    content = re.sub(r'href="#" class="btn btn-primary nav-cta(?:-desktop)?">Abra sua Empresa',
                     r'href="#abra-empresa" class="btn btn-primary nav-cta">Abra sua Empresa',
                     content)

    # Footer/nav "Abrir empresa grátis" -> #abra-empresa
    content = re.sub(r'href="#" class="btn btn-primary">Abrir empresa grátis',
                     r'href="#abra-empresa" class="btn btn-primary">Abrir empresa grátis',
                     content)
    content = re.sub(r'href="#" class="btn btn-primary">Abra sua Empresa Grátis',
                     r'href="#abra-empresa" class="btn btn-primary">Abra sua Empresa Grátis',
                     content)

    # === SERVICE LINKS (Ver vantagens / Saiba mais / Vantagens) ===
    # These should open modals - use javascript:void(0) with onclick
    content = re.sub(r'href="#" class="service-link"[^>]*>Ver vantagens</a>',
                     r'href="javascript:void(0)" onclick="openModal(\'modal-consultoria\')" class="service-link">Ver vantagens</a>',
                     content)
    content = re.sub(r'href="#" class="service-link"[^>]*>Vantagens →</a>',
                     r'href="javascript:void(0)" onclick="openModal(\'modal-consultoria\')" class="service-link">Vantagens →</a>',
                     content)
    content = re.sub(r'href="#" class="service-link"[^>]*>VANTAGENS →</a>',
                     r'href="javascript:void(0)" onclick="openModal(\'modal-consultoria\')" class="service-link">VANTAGENS →</a>',
                     content)
    content = re.sub(r'href="#" class="service-link"[^>]*>Saiba mais</a>',
                     r'href="javascript:void(0)" onclick="openModal(\'modal-consultoria\')" class="service-link">Saiba mais</a>',
                     content)
    content = re.sub(r'href="#" class="service-link neu-btn">Vantagens →</a>',
                     r'href="javascript:void(0)" onclick="openModal(\'modal-consultoria\')" class="service-link neu-btn">Vantagens →</a>',
                     content)

    # "Ver Vantagens" button (not service-link class)
    content = re.sub(r'href="#" class="btn btn-primary">Ver Vantagens</a>',
                     r'href="javascript:void(0)" onclick="openModal(\'modal-consultoria\')" class="btn btn-primary">Ver Vantagens</a>',
                     content)

    # === PROPOSAL/CTA BUTTONS ===
    # "Solicitar proposta" -> WhatsApp
    content = re.sub(r'href="#" class="btn btn-primary">Solicitar proposta',
                     r'href="https://wa.me/5511981050614?text=Olá, gostaria de solicitar uma proposta" target="_blank" class="btn btn-primary">Solicitar proposta',
                     content)
    content = re.sub(r'href="#" class="btn btn-white">Solicitar proposta',
                     r'href="https://wa.me/5511981050614?text=Olá, gostaria de solicitar uma proposta" target="_blank" class="btn btn-white">Solicitar proposta',
                     content)
    content = re.sub(r'href="#" class="btn btn-gold">Solicitar Proposta',
                     r'href="https://wa.me/5511981050614?text=Olá, gostaria de solicitar uma proposta" target="_blank" class="btn btn-gold">Solicitar Proposta',
                     content)
    content = re.sub(r'href="#" class="btn btn-gold">Agendar Reunião',
                     r'href="https://wa.me/5511981050614?text=Olá, gostaria de agendar uma reunião" target="_blank" class="btn btn-gold">Agendar Reunião',
                     content)

    # === FOOTER NAV LINKS ===
    # Sobre -> #sobre (or #valores if no sobre section)
    content = re.sub(r'<li><a href="#">Sobre</a></li>',
                     r'<li><a href="#sobre">Sobre</a></li>',
                     content)
    # Contato -> #contato
    content = re.sub(r'<li><a href="#">Contato</a></li>',
                     r'<li><a href="#contato">Contato</a></li>',
                     content)

    # Legal pages - keep as # since they don't exist yet
    # (Política de Cookies, Termos, Privacidade stay as #)

    # === SERVICE LIST ITEMS IN FOOTER ===
    content = re.sub(r'<li><a href="#">MEI</a></li>',
                     r'<li><a href="#mei">MEI</a></li>',
                     content)
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

    # === CONTACT INFO ===
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
