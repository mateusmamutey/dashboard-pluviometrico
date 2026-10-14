/* Desenho do pluviômetro Ville de Paris em corte, comum ao componente
   do pluviômetro e ao da torneira. O Python injeta este arquivo no
   marcador de instrumento de cada .html.

   Geometria: funil coletor, pescoço, reservatório cônico com a ponta
   para baixo e torneira na ponta. Num cone, o volume cresce com o cubo
   da altura, então a altura da água é H * (mm / capacidade)^(1/3):
   os primeiros milímetros sobem rápido, perto do topo sobe devagar.
   A régua ao lado é linear em mm, para contraste. */

const NS = 'http://www.w3.org/2000/svg';
const reduzMovimento = matchMedia('(prefers-reduced-motion: reduce)').matches;
const fmt = (n, d = 1) => Number(n).toLocaleString('pt-BR', {minimumFractionDigits: d, maximumFractionDigits: d});

function el(tag, attrs, pai) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (pai) pai.appendChild(e);
  return e;
}
function txt(pai, x, y, s, extra) {
  const t = el('text', Object.assign({x, y, 'font-family': 'IBM Plex Mono, monospace', 'font-size': 10.5, fill: 'var(--ink-3)'}, extra || {}), pai);
  t.textContent = s;
  return t;
}

const GEO = {cx: 110, R: 60, yTopo: 120, yPonta: 318, H: 198};
const alturaCone = f => GEO.H * Math.cbrt(Math.max(0, Math.min(1, f)));

function faixaDe(mm, cfg) {
  if (mm == null) return 'sem_dados';
  const pct = mm / cfg.capacidade * 100;
  if (pct >= cfg.urgente) return 'urgente';
  if (pct >= cfg.atencao) return 'atencao';
  return 'tranquilo';
}

const SELOS = {
  tranquilo: '<svg viewBox="0 0 12 12"><circle cx="6" cy="6" r="4.5" fill="currentColor"/></svg>Tranquilo',
  atencao: '<svg viewBox="0 0 12 12"><path d="M6 1 11 10H1Z" fill="currentColor"/></svg>Atenção',
  urgente: '<svg viewBox="0 0 12 12"><path d="M4 1h4l3 3v4l-3 3H4L1 8V4Z" fill="currentColor"/></svg>Urgente',
  sem_dados: '<svg viewBox="0 0 12 12"><circle cx="6" cy="6" r="4" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>Sem dados'
};
function selo(elemento, faixa) {
  elemento.className = 'chip ' + faixa;
  elemento.innerHTML = SELOS[faixa];
}

/* op: {marcas, regua, proveta}; cfg: {capacidade, atencao, urgente, escalaProveta} */
function criarInstrumento(host, op, cfg) {
  const {cx, R, yTopo, yPonta, H} = GEO;
  const alto = op.proveta ? 560 : 372;
  const svg = el('svg', {viewBox: `0 0 240 ${alto}`, role: 'img', 'aria-label': 'Pluviômetro Ville de Paris em corte'}, host);
  svg.style.width = '100%';
  svg.style.height = 'auto';
  svg.style.display = 'block';
  svg.style.maxHeight = op.proveta ? '470px' : '330px';

  const metal = {fill: 'var(--metal-1)', stroke: 'var(--metal-2)', 'stroke-width': 1.5};
  el('rect', Object.assign({x: cx - 62, y: 16, width: 124, height: 16, rx: 2}, metal), svg);
  el('polygon', Object.assign({points: `${cx - 62},32 ${cx + 62},32 ${cx + 7},90 ${cx - 7},90`}, metal), svg);
  el('rect', Object.assign({x: cx - 7, y: 90, width: 14, height: 26}, metal), svg);
  el('rect', Object.assign({x: cx - R - 4, y: yTopo - 6, width: 2 * R + 8, height: 7, rx: 2}, metal), svg);
  const corpo = el('polygon', {points: `${cx - R},${yTopo} ${cx + R},${yTopo} ${cx},${yPonta}`, fill: 'var(--surface-2)', stroke: 'var(--metal-2)', 'stroke-width': 2.5, 'stroke-linejoin': 'round'}, svg);
  const agua = el('polygon', {points: '', fill: 'var(--water)', 'fill-opacity': .88}, svg);
  const superficie = el('line', {stroke: 'var(--water-soft)', 'stroke-width': 1.6}, svg);
  const gMarcas = el('g', {}, svg);

  // torneira
  el('rect', {x: cx - 3, y: yPonta - 2, width: 6, height: 16, fill: 'var(--metal-2)'}, svg);
  el('rect', Object.assign({x: cx - 9, y: yPonta + 12, width: 18, height: 14, rx: 3}, metal), svg);
  el('rect', {x: cx - 2.5, y: yPonta + 26, width: 5, height: 12, fill: 'var(--metal-2)'}, svg);
  const alavanca = el('rect', {x: cx - 20, y: yPonta + 16, width: 40, height: 6, rx: 3, fill: 'var(--ink-2)'}, svg);
  if (!op.proveta) txt(svg, cx, yPonta + 52, 'torneira', {'text-anchor': 'middle'});

  const xr = 200;
  let gRegua, marcador, conector, jato, provAgua, prov;
  if (op.regua) {
    gRegua = el('g', {}, svg);
    conector = el('line', {stroke: 'var(--ink-3)', 'stroke-dasharray': '3 3', 'stroke-width': 1}, svg);
    marcador = el('polygon', {fill: 'var(--ink)'}, svg);
  }
  if (op.proveta) {
    const px = cx - 18, pw = 36, pt = 372, pb = 550;
    jato = el('rect', {x: cx - 1.5, y: yPonta + 38, width: 3, height: 0, fill: 'var(--water)'}, svg);
    el('rect', {x: px, y: pt, width: pw, height: pb - pt, rx: 3, fill: 'var(--glass)', stroke: 'var(--ink-3)', 'stroke-width': 1.5}, svg);
    provAgua = el('rect', {x: px + 2, y: pb, width: pw - 4, height: 0, fill: 'var(--water)', 'fill-opacity': .88}, svg);
    const escala = cfg.escalaProveta;
    const passo = escala > 150 ? 50 : 25;
    for (let v = 0; v <= escala + 0.01; v += passo / 2) {
      const y = pb - (pb - pt - 8) * v / escala;
      const maior = Math.abs(v / passo - Math.round(v / passo)) < .01;
      el('line', {x1: px + pw - (maior ? 12 : 7), y1: y, x2: px + pw, y2: y, stroke: 'var(--ink-3)', 'stroke-width': 1}, svg);
      if (maior) txt(svg, px + pw + 6, y + 3.5, String(v), {'font-size': 10});
    }
    txt(svg, px + pw + 6, pb + 14, 'proveta (mm)', {'font-size': 10});
    prov = {pt, pb};
  }

  function configurar() {
    gMarcas.innerHTML = '';
    if (op.marcas) {
      [[cfg.atencao, 'var(--warn)'], [cfg.urgente, 'var(--crit)']].forEach(([p, c]) => {
        const h = alturaCone(p / 100), y = yPonta - h, r = R * h / H;
        el('line', {x1: cx - r, y1: y, x2: cx + r, y2: y, stroke: c, 'stroke-width': 1.6, 'stroke-dasharray': '5 4'}, gMarcas);
        txt(gMarcas, cx - r - 5, y + 3.5, Math.round(p) + '%', {'text-anchor': 'end', fill: c});
      });
    }
    if (!op.regua) return;
    gRegua.innerHTML = '';
    const cap = cfg.capacidade;
    const yv = v => yPonta - H * v / cap;
    el('rect', {x: xr - 3, y: yv(cap), width: 3, height: yv(cap * cfg.urgente / 100) - yv(cap), fill: 'var(--crit)'}, gRegua);
    el('rect', {x: xr - 3, y: yv(cap * cfg.urgente / 100), width: 3, height: yv(cap * cfg.atencao / 100) - yv(cap * cfg.urgente / 100), fill: 'var(--warn)'}, gRegua);
    el('line', {x1: xr, y1: yTopo, x2: xr, y2: yPonta, stroke: 'var(--ink-3)', 'stroke-width': 1.2}, gRegua);
    const passo = cap > 300 ? 100 : cap > 150 ? 40 : 25;
    for (let v = 0; v <= cap + .01; v += passo / 2) {
      const maior = Math.abs(v / passo - Math.round(v / passo)) < .01;
      el('line', {x1: xr, y1: yv(v), x2: xr + (maior ? 7 : 4), y2: yv(v), stroke: 'var(--ink-3)', 'stroke-width': 1}, gRegua);
      if (maior && cap - v > passo * .45) txt(gRegua, xr + 10, yv(v) + 3.5, String(v), {'font-size': 10});
    }
    el('line', {x1: xr, y1: yTopo, x2: xr + 7, y2: yTopo, stroke: 'var(--ink-3)'}, gRegua);
    txt(gRegua, xr + 10, yTopo + 3.5, String(Math.round(cap)), {'font-size': 10, fill: 'var(--ink)'});
    txt(gRegua, xr + 4, yPonta + 18, 'mm', {'text-anchor': 'middle', 'font-size': 10});
    txt(gRegua, xr + 4, yPonta + 30, 'linear', {'text-anchor': 'middle', 'font-size': 10});
  }

  function nivel(mm) {
    const f = Math.max(0, mm) / cfg.capacidade, h = alturaCone(f), y = yPonta - h, r = R * h / H;
    const visivel = h > .3;
    agua.setAttribute('points', visivel ? `${cx - r},${y} ${cx + r},${y} ${cx},${yPonta}` : '');
    Object.entries({x1: cx - r, y1: y, x2: cx + r, y2: y}).forEach(([k, v]) => superficie.setAttribute(k, v));
    superficie.style.display = visivel ? '' : 'none';
    const faixa = op.marcas ? faixaDe(mm, cfg) : 'tranquilo';
    corpo.setAttribute('stroke', faixa === 'atencao' ? 'var(--warn)' : faixa === 'urgente' ? 'var(--crit)' : 'var(--metal-2)');
    corpo.setAttribute('stroke-width', faixa === 'tranquilo' ? 2.5 : 3.5);
    if (op.regua) {
      const yl = yPonta - H * Math.min(f, 1);
      marcador.setAttribute('points', `${xr - 2},${yl} ${xr - 10},${yl - 5} ${xr - 10},${yl + 5}`);
      Object.entries({x1: cx + r, y1: y, x2: xr - 10, y2: yl}).forEach(([k, v]) => conector.setAttribute(k, v));
      conector.style.display = visivel ? '' : 'none';
    }
  }

  function torneira(graus) {
    alavanca.setAttribute('transform', `rotate(${graus} ${cx} ${yPonta + 19})`);
  }

  function proveta(mm, jorrando) {
    if (!op.proveta) return;
    const hh = (prov.pb - prov.pt - 8) * Math.min(Math.max(mm, 0), cfg.escalaProveta) / cfg.escalaProveta;
    provAgua.setAttribute('y', prov.pb - hh);
    provAgua.setAttribute('height', hh);
    jato.setAttribute('height', jorrando ? Math.max(0, prov.pb - hh - (yPonta + 38)) : 0);
  }

  configurar();
  return {nivel, torneira, proveta};
}

/* Anima de a até b chamando fn(valor) a cada quadro. */
function tween(ms, fn) {
  return new Promise(res => {
    if (reduzMovimento) { fn(1); return res(); }
    const t0 = performance.now();
    (function f(t) {
      const p = Math.min(1, (t - t0) / ms);
      fn(p);
      p < 1 ? requestAnimationFrame(f) : res();
    })(t0);
  });
}
const suave = p => p < .5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
const espera = ms => new Promise(r => setTimeout(r, reduzMovimento ? 0 : ms));
