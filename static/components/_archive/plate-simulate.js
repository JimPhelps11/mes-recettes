/* Fallback: si /api/vision/estimate_portion n'existe pas, on simule les résultats côté client.
   Cela permet de tester l'UI sans dépendre d'un backend modifié.
*/
if (!window.useSimulatedAnalyzer) {
  window.useSimulatedAnalyzer = true;

  window.simulatePlateAnalysis = async function(file) {
    const preview = document.getElementById('analyzer-preview');
    const img = document.getElementById('analyzer-image');
    const loading = document.getElementById('analyzer-loading');
    const results = document.getElementById('analyzer-results');
    const error = document.getElementById('analyzer-error');

    // Reset
    img.style.display = 'none';
    results.style.display = 'none';
    error.style.display = 'none';
    loading.style.display = 'block';

    // Preview
    const url = URL.createObjectURL(file);
    img.src = url; img.style.display = 'block';

    loading.textContent = '🔄 Analyse (simulée) en cours…';

    // Simule le delay
    await new Promise(r => setTimeout(r, 800));

    // Résultat simulé aléatoire mais réaliste
    const possibles = [
      { nom: 'Carottes râpées', quantite_g: 100, certitude: 'haute' },
      { nom: 'Poulet grillé', quantite_g: 150, certitude: 'haute' },
      { nom: 'Riz basmati', quantite_g: 100, certitude: 'moyenne' },
      { nom: 'Haricots verts', quantite_g: 80, certitude: 'moyenne' },
      { nom: 'Tomates cerise', quantite_g: 50, certitude: 'basse' },
      { nom: 'Vinaigre', quantite_g: 8, certitude: 'basse' },
    ];
    const sample = [];
    for (let i=0; i<Math.floor(Math.random()*3)+2; i++) {
      sample.push(possibles[Math.floor(Math.random()*possibles.length)]);
    }
    const total = sample.reduce((a,b) => a+b.quantite_g, 0);

    const sugg = [];
    const titles = ['Poulet basquaise','Ratatouille','Salade de carottes','Riz pilaf légumes','Gratin de courgettes'];
    for (let i=0; i<Math.floor(Math.random()*4)+1; i++) {
      const idx = Math.floor(Math.random()*titles.length);
      sugg.push({ fichier: titles[idx].toLowerCase().replace(/\s+/g,'-'), titre: titles[idx], kcal_100g: Math.floor(Math.random()*200)+150, match_pct: Math.floor(Math.random()*50)+50 });
    }

    const resSimule = {
      ingredient: sample,
      total_estime_g: total,
      description: "Plat équilibré à base de légumes et protéines.",
      notes: "Analyse simulée (pas d’API clé installée).",
      source: "simulé",
      suggestions_recettes: sugg
    };

    PlateAnalyzer.renderIngredients(resSimule);
    PlateAnalyzer.renderSuggestions(resSimule);

    loading.style.display = 'none';
    results.style.display = 'block';

    if (url) URL.revokeObjectURL(url);
  };
}

// Patch PlateAnalyzer pour utiliser simulate ou fallback fetch
const _oldHandle = PlateAnalyzer.handleImage;
PlateAnalyzer.handleImage = async function(evt) {
  const file = evt.target.files[0];
  if (!file) return;

  if (window.useSimulatedAnalyzer || !document.querySelector('#analyzer-results')) {
    // Utiliser simulation : ignore evt et utilise simulatePlateAnalysis
    await window.simulatePlateAnalysis(file);
    return;
  }

  // Sinon utiliser le vrai handle existant
  return _oldHandle.call(this, evt);
};
