#!/usr/bin/env python3
"""
Adapt all empresarial models with the same features as modelo-1-editorial:
- Abra Empresa Gratis section with form
- MEI section with benefits
- Modals for each service advantages
- Fix orphan links
"""
import re
import glob

# Models to adapt (excluding modelo-1 which is already done)
models = sorted(glob.glob('servicos/portal/modelos/empresarial/modelo-*.html'))
models = [m for m in models if 'modelo-1-editorial' not in m]

print(f'Found {len(models)} models to adapt')

for model_path in models:
    print(f'\nProcessing: {model_path}')

    with open(model_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check if already adapted (has abra-empresa section)
    if 'id="abra-empresa"' in content:
        print('  Already adapted, skipping...')
        continue

    # Find the position before WhatsApp float and closing scripts
    # Look for pattern: </footer>\n\n<a href="https://wa.me..." class="wa-float"
    match = re.search(r'(</footer>)\s*(<a href="https://wa\.me)', content, re.DOTALL)

    if not match:
        print('  WARNING: Could not find footer/wa-float pattern')
        continue

    insert_pos = match.start(2)  # Position before <a href="https://wa.me

    # Sections to insert
    sections_to_add = '''
<!-- SEÇÃO ABRIR EMPRESA -->
<section id="abra-empresa" style="background:var(--bg-2);">
  <div class="page-wrapper"><div class="wrap">
    <div class="section-head reveal">
      <div class="section-tag">Comece Agora</div>
      <h2>Abra sua Empresa <em>Grátis</em></h2>
      <p>Preencha o formulário e nossa equipe entrará em contato em até 24 horas.</p>
    </div>
    <div style="max-width:700px;margin:0 auto;" class="reveal">
      <form onsubmit="event.preventDefault(); alert('Obrigado! Entraremos em contato em breve.'); this.reset();" style="background:white;padding:40px;border-radius:20px;border:1px solid var(--line);">
        <div style="margin-bottom:20px;">
          <label style="display:block;font-weight:600;margin-bottom:8px;font-size:14px;">Nome Completo *</label>
          <input type="text" required placeholder="Seu nome completo" style="width:100%;padding:12px 16px;border:1px solid var(--line);border-radius:8px;font-size:15px;">
        </div>
        <div style="margin-bottom:20px;">
          <label style="display:block;font-weight:600;margin-bottom:8px;font-size:14px;">E-mail *</label>
          <input type="email" required placeholder="seu@email.com" style="width:100%;padding:12px 16px;border:1px solid var(--line);border-radius:8px;font-size:15px;">
        </div>
        <div style="margin-bottom:20px;">
          <label style="display:block;font-weight:600;margin-bottom:8px;font-size:14px;">WhatsApp *</label>
          <input type="tel" required placeholder="(11) 99999-9999" style="width:100%;padding:12px 16px;border:1px solid var(--line);border-radius:8px;font-size:15px;">
        </div>
        <div style="margin-bottom:20px;">
          <label style="display:block;font-weight:600;margin-bottom:8px;font-size:14px;">Atividade Principal</label>
          <select style="width:100%;padding:12px 16px;border:1px solid var(--line);border-radius:8px;font-size:15px;">
            <option value="">Selecione...</option>
            <option>Comércio</option>
            <option>Serviços</option>
            <option>Indústria</option>
            <option>Outros</option>
          </select>
        </div>
        <div style="margin-bottom:24px;">
          <label style="display:block;font-weight:600;margin-bottom:8px;font-size:14px;">Observações</label>
          <textarea placeholder="Conte-nos sobre seu negócio..." rows="4" style="width:100%;padding:12px 16px;border:1px solid var(--line);border-radius:8px;font-size:15px;resize:vertical;"></textarea>
        </div>
        <button type="submit" class="btn btn-primary" style="width:100%;">Solicitar Abertura Grátis →</button>
      </form>
    </div>
  </div>
</section>

<!-- SEÇÃO MEI -->
<section id="mei" style="background:var(--accent-2);color:white;">
  <div class="page-wrapper"><div class="wrap">
    <div class="section-head reveal">
      <div class="section-tag" style="color:var(--accent-3);">Para Autônomos</div>
      <h2 style="color:white;">Contabilidade <em>MEI</em></h2>
      <p style="color:rgba(255,255,255,0.8);">Solução completa para Microempreendedores Individuais.</p>
    </div>
    <div style="display:grid;gap:40px;align-items:center;" class="reveal">
      <div>
        <ul style="list-style:none;margin-bottom:32px;">
          <li style="padding:8px 0;display:flex;align-items:center;gap:12px;font-size:15px;"><span style="color:var(--accent-3);">★</span> DAS mensal pago automaticamente</li>
          <li style="padding:8px 0;display:flex;align-items:center;gap:12px;font-size:15px;"><span style="color:var(--accent-3);">★</span> Emissão de notas fiscais</li>
          <li style="padding:8px 0;display:flex;align-items:center;gap:12px;font-size:15px;"><span style="color:var(--accent-3);">★</span> Relatório anual (RAIS)</li>
          <li style="padding:8px 0;display:flex;align-items:center;gap:12px;font-size:15px;"><span style="color:var(--accent-3);">★</span> Alteração de dados cadastrais</li>
          <li style="padding:8px 0;display:flex;align-items:center;gap:12px;font-size:15px;"><span style="color:var(--accent-3);">★</span> Orientação tributária</li>
          <li style="padding:8px 0;display:flex;align-items:center;gap:12px;font-size:15px;"><span style="color:var(--accent-3);">★</span> App exclusivo MEI</li>
        </ul>
        <a href="https://wa.me/5511981050614?text=Olá, gostaria de saber sobre contabilidade MEI" target="_blank" class="btn btn-primary">Contratar MEI →</a>
      </div>
      <div style="background:rgba(255,255,255,0.1);backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,0.2);border-radius:16px;padding:32px;text-align:center;">
        <div style="font-size:18px;font-weight:600;margin-bottom:16px;">Planos a partir de</div>
        <div style="font-size:14px;opacity:0.8;margin-bottom:24px;">Valores especiais para MEI com todas as obrigações incluídas</div>
        <a href="https://wa.me/5511981050614?text=Olá, gostaria de saber os valores para contabilidade MEI" target="_blank" class="btn btn-outline" style="border-color:white;color:white;width:100%;">Consultar Valores →</a>
      </div>
    </div>
  </div>
</section>

<!-- MODAIS DE VANTAGENS -->
<div id="modal-consultoria" class="modal-overlay" onclick="closeModal(event)">
  <div class="modal" onclick="event.stopPropagation()">
    <button class="modal-close" onclick="closeModal()">&times;</button>
    <h3>Vantagens da Consultoria</h3>
    <ul class="vantagens-list">
      <li>Análise tributária personalizada para redução legal de impostos</li>
      <li>Planejamento financeiro estratégico para crescimento sustentável</li>
      <li>Relatórios gerenciais mensais com indicadores-chave</li>
      <li>Acesso a especialistas em direito tributário e societário</li>
      <li>Reuniões trimestrais de acompanhamento estratégico</li>
      <li>Suporte ilimitado via WhatsApp e e-mail</li>
      <li>Dashboard online com visão em tempo real</li>
    </ul>
  </div>
</div>

<div id="modal-legalizacao" class="modal-overlay" onclick="closeModal(event)">
  <div class="modal" onclick="event.stopPropagation()">
    <button class="modal-close" onclick="closeModal()">&times;</button>
    <h3>Vantagens da Legalização</h3>
    <ul class="vantagens-list">
      <li>Abertura 100% online sem necessidade de deslocamento</li>
      <li>Sem taxa de abertura para clientes de assessoria mensal</li>
      <li>CNPJ emitido em até 5 dias úteis</li>
      <li>Inscrições estadual e municipal incluídas</li>
      <li>Alvará de funcionamento regularizado</li>
      <li>Contrato social elaborado por especialistas</li>
      <li>Enquadramento tributário otimizado desde o início</li>
      <li>Acompanhamento completo até a emissão do CNPJ</li>
    </ul>
  </div>
</div>

<div id="modal-assessoria" class="modal-overlay" onclick="closeModal(event)">
  <div class="modal" onclick="event.stopPropagation()">
    <button class="modal-close" onclick="closeModal()">&times;</button>
    <h3>Vantagens da Assessoria</h3>
    <ul class="vantagens-list">
      <li>Contabilidade consultiva focada no seu negócio</li>
      <li>Gestão completa de obrigações fiscais e trabalhistas</li>
      <li>Folha de pagamento processada com precisão</li>
      <li>Escrituração contábil e fiscal em dia</li>
      <li>Sped Fiscal, Sped Contábil e DCTF entregues no prazo</li>
      <li>Relatórios mensais de desempenho</li>
      <li>Contador dedicado disponível para dúvidas</li>
      <li>App exclusivo para envio de documentos</li>
    </ul>
  </div>
</div>

<div id="modal-pericia" class="modal-overlay" onclick="closeModal(event)">
  <div class="modal" onclick="event.stopPropagation()">
    <button class="modal-close" onclick="closeModal()">&times;</button>
    <h3>Vantagens da Perícia Contábil</h3>
    <ul class="vantagens-list">
      <li>Cálculos judiciais precisos e fundamentados</li>
      <li>Revisão contratual detalhada com identificação de riscos</li>
      <li>Avaliação de empresas para fusões e aquisições</li>
      <li>Laudos periciais aceitos em tribunais</li>
      <li>Expertise em direito empresarial e societário</li>
      <li>Atuação em processos trabalhistas e cíveis</li>
      <li>Relatórios técnicos completos e claros</li>
      <li>Sigilo absoluto em todas as informações</li>
    </ul>
  </div>
</div>

<style>
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); backdrop-filter: blur(4px); z-index: 2000; display: none; align-items: center; justify-content: center; padding: 20px; }
.modal-overlay.active { display: flex; }
.modal { background: white; border-radius: 20px; max-width: 600px; width: 100%; max-height: 90vh; overflow-y: auto; padding: 40px; position: relative; }
.modal-close { position: absolute; top: 16px; right: 16px; width: 36px; height: 36px; border-radius: 50%; border: none; background: var(--line); cursor: pointer; font-size: 20px; display: flex; align-items: center; justify-content: center; }
.modal-close:hover { background: var(--accent); color: white; }
.modal h3 { font-family: inherit; font-size: 28px; margin-bottom: 24px; color: var(--ink); }
.vantagens-list { list-style: none; }
.vantagens-list li { padding: 12px 0; border-bottom: 1px solid var(--line); display: flex; align-items: start; gap: 12px; font-size: 15px; color: var(--ink-2); }
.vantagens-list li:last-child { border-bottom: none; }
.vantagens-list li::before { content: '✓'; color: var(--accent); font-weight: 700; flex-shrink: 0; }
</style>

<script>
function openModal(id) { document.getElementById(id).classList.add('active'); document.body.style.overflow = 'hidden'; }
function closeModal(e) { if (!e || e.target.classList.contains('modal-overlay') || e.target.classList.contains('modal-close')) { document.querySelectorAll('.modal-overlay').forEach(m => m.classList.remove('active')); document.body.style.overflow = ''; } }
document.addEventListener('keydown', function(e) { if (e.key === 'Escape') closeModal(); });
</script>

'''

    # Insert sections before wa-float
    content = content[:insert_pos] + sections_to_add + content[insert_pos:]

    # Fix common orphan links
    content = re.sub(r'href="#" class="brand"', r'href="/" class="brand"', content)
    content = re.sub(r'href="#">Início</a>', r'href="/">Início</a>', content)
    content = re.sub(r'href="#">Abrir', r'href="#abra-empresa">Abrir', content)
    content = re.sub(r'href="#">Solicitar proposta', r'href="https://wa.me/5511981050614?text=Olá, gostaria de solicitar uma proposta" target="_blank">Solicitar proposta', content)

    with open(model_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print('  Done!')

print('\n=== All models adapted ===')
