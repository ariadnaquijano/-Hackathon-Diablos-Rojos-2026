// Stuff+ del simulador calculado en el navegador: misma cuenta que score() en src/simulador.py,
// con los árboles exportados del modelo oficial. src/verificar_simulador.py compara las dos.
const MotorStuff = (() => {
  const FASTBALL = "Four-Seam";
  const INPUTS = ["RelSpeed", "SpinRate", "SpinAxis", "InducedVertBreak", "HorzBreak", "RelHeight", "RelSide", "Extension"];

  function armSide(profile, prefix = "") {
    const sign = profile.pitcher_hand === "Left" ? -1 : 1, axis = profile[prefix + "SpinAxis"];
    return { hb: profile[prefix + "HorzBreak"] * sign, rel_side: profile[prefix + "RelSide"] * sign, axis: sign < 0 ? 360 - axis : axis };
  }

  function pitchRow(model, profile, air) {
    const type = profile.pitch_class, measured = profile.aire_medido;
    const k = model.k[type], kFb = model.k[FASTBALL];
    const own = armSide(profile), fb = armSide(profile, "fb_");
    const ivbSea = profile.InducedVertBreak / measured ** k.ivb, hbSea = own.hb / measured ** k.hb;
    const fbIvbSea = profile.fb_InducedVertBreak / measured ** kFb.ivb, fbHbSea = fb.hb / measured ** kFb.hb;
    const ivb = ivbSea * air ** k.ivb, hb = hbSea * air ** k.hb;
    const releaseGap = Math.hypot(profile.RelHeight - profile.fb_RelHeight, own.rel_side - fb.rel_side);
    return {
      RelSpeed: profile.RelSpeed, SpinRate: profile.SpinRate, spin_axis_arm: own.axis,
      RelHeight: profile.RelHeight, rel_side_arm: own.rel_side, Extension: profile.Extension,
      vaa_rel: profile.vaa_rel, InducedVertBreak: ivb, hb_arm_side: hb, ivb_sea_level: ivbSea, hb_sea_level: hbSea,
      velo_diff_vs_fb: profile.RelSpeed - profile.fb_RelSpeed,
      ivb_diff_vs_fb: ivb - fbIvbSea * air ** kFb.ivb,
      hb_diff_vs_fb: hb - fbHbSea * air ** kFb.hb,
      axis_diff_vs_fb: (((own.axis - fb.axis + 540) % 360) + 360) % 360 - 180,
      release_dist_vs_fb: Math.hypot(releaseGap, model.dispersion_salida),
      extension_diff_vs_fb: profile.Extension - profile.fb_Extension,
      pitch_class: type, pitcher_hand: profile.pitcher_hand,
    };
  }

  // Un árbol de HistGradientBoosting: categóricas por conjunto de categorías a la izquierda, numéricas por umbral.
  function leaf(tree, x) {
    let node = 0;
    while (tree.f[node] >= 0) {
      const value = x[tree.f[node]], cats = tree.c[node];
      const left = cats >= 0 ? ((cats >>> value) & 1) === 1 : value <= tree.t[node];
      node = left ? tree.l[node] : tree.r[node];
    }
    return tree.t[node];
  }

  function predict(component, encoded) {
    const raw = component.trees.reduce((total, tree) => total + leaf(tree, encoded), component.base);
    return component.kind === "clasificador" ? 1 / (1 + Math.exp(-raw)) : raw;
  }

  function encode(model, row) {
    return model.orden.map(name => name in model.categorias ? model.categorias[name].indexOf(row[name]) : row[name]);
  }

  function combine(p, v) {
    const contact = p.p_foul * v.foul + (1 - p.p_foul) * (p.valor_batazo - v.conteo_batazo);
    const swing = p.p_whiff * v.whiff + (1 - p.p_whiff) * contact;
    const take = p.p_strike * v.strike + (1 - p.p_strike) * v.bola;
    return p.p_swing * swing + (1 - p.p_swing) * take;
  }

  // Promedio contra los dos lados del bateador, como pitch_rows() en Python.
  function runs(model, row) {
    const values = ["True", "False"].map(side => {
      const encoded = encode(model, { ...row, platoon_same_side: side });
      const predicted = Object.fromEntries(Object.entries(model.componentes).map(([name, c]) => [name, predict(c, encoded)]));
      return combine(predicted, model.valores);
    });
    return (values[0] + values[1]) / 2;
  }

  // Mismos límites físicos que validate() en Python: fuera de ellos el valor no es un pitch posible.
  function problem(model, input) {
    const prefixes = input.pitch_class === FASTBALL ? [""] : ["", "fb_"];
    for (const prefix of prefixes) {
      for (const [key, [low, high]] of Object.entries(model.limites)) {
        if (prefix && key === "SpinRate") continue;
        const value = input[prefix + key], owner = prefix ? "de la recta de referencia" : "del pitch";
        const label = model.etiquetas[key];
        if (!Number.isFinite(value)) return `${label[0].toUpperCase() + label.slice(1)} ${owner} debe ser un número.`;
        if (value < low || value > high) return `${label[0].toUpperCase() + label.slice(1)} ${owner} debe estar entre ${low} y ${high}.`;
      }
    }
    return null;
  }

  const round = (value, digits) => Math.round(value * 10 ** digits) / 10 ** digits;

  function score(model, input) {
    const type = input.pitch_class;
    let profile = { ...input, vaa_rel: model.valores_tipicos[type].vaa_rel };
    if (type === FASTBALL) for (const key of INPUTS) profile["fb_" + key] = profile[key];
    const sea = pitchRow(model, profile, model.aire.mar), harp = pitchRow(model, profile, model.aire.harp);
    const movement = { mar: { ivb: round(sea.InducedVertBreak, 1), hb: round(sea.hb_arm_side, 1) },
                       harp: { ivb: round(harp.InducedVertBreak, 1), hb: round(harp.hb_arm_side, 1) } };
    const scale = model.escala[type];
    if (scale.perfiles < model.min_perfiles) return { stuff_plus: null, stuff_plus_harp: null, perfiles: scale.perfiles, ...movement };
    const stuffPlus = 100 - 10 * (runs(model, sea) - scale.media) / scale.desviacion;
    const delta = model.delta_harp[type];
    return { stuff_plus: round(stuffPlus, 1), stuff_plus_harp: delta == null ? null : round(stuffPlus + delta, 1),
             perdida_liga_por_100: model.perdida_liga[type] ?? null, perfiles: scale.perfiles, ...movement };
  }

  return { score, problem };
})();
if (typeof module !== "undefined") module.exports = MotorStuff;
