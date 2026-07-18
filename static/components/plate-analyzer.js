/**
 * PlateAnalyzer – analyse une photo depuis /api/analyze_plate
 * Retourne : ingredients[] + total_estime_g + suggestions_recettes[]
 */
class PlateAnalyzer {
  static UPLOAD_BUTTON_ID = 'ia-vision-upload'
  static RESULT_ID = 'ia-vision-result'

  static init() {
    const uploadBtn = document.getElementById(this.UPLOAD_BUTTON_ID)
    const dropZone = document.getElementById('ia-vision-drop')
    if (!uploadBtn || !dropZone) return

    ;['dragover','drop'].forEach(e => {
      dropZone.addEventListener(e, (ev) => {
        ev.preventDefault()
        if (e==='dragover') { dropZone.style.border='3px dashed #4285f4'; return }
        dropZone.style.border='3px dashed #99c';
        if (ev.dataTransfer?.files?.[0]) {
          uploadBtn.files = ev.dataTransfer.files
          this.handleImage({target:{files: ev.dataTransfer.files}})
        }
      })
    })

    uploadBtn.addEventListener('change', this.handleImage.bind(this))
  }

  static async handleImage(evt) {
    const file = evt.target.files?.[0]
    if (!file) return

    const preview = document.getElementById('analyzer-preview')
    const img = document.getElementById('analyzer-image')
    const loading = document.getElementById('analyzer-loading')
    const result = document.getElementById(this.RESULT_ID)
    const error = document.getElementById('analyzer-error')

    if (preview) preview.style.display='block'
    if (img) {
      img.src = URL.createObjectURL(file)
      img.style.display='block'
    }
    if (loading) loading.style.display='none'
    if (error) error.textContent=''

    try {
      const form = new FormData()
      form.append('image', file)
      const res = await fetch('/api/analyze_plate', {method:'POST', body:form})
      const data = await res.json()
      await this.renderResults(data)
    } catch(e){
      if (error) error.textContent = `Erreur IA: ${e.message}`
      console.error('analyse error', e)
    }
  }

  static async renderResults(data){
    const result = document.getElementById(this.RESULT_ID)
    if (!result) return

    const section = document.createElement('section')
    result.innerHTML = ''
    result.style.display = 'block'

    const h4 = document.createElement('h4')
    h4.textContent = '🧾 Résultat de l’analyse'
    h4.style.marginBottom='12px'
    section.appendChild(h4)

    // Ingrédients
    const ul = document.createElement('ul')
    ul.style.listStyle='none'; ul.style.padding=0; ul.style.lineHeight='1.6em'
    data.ingredients.forEach(ing => {
      const li = document.createElement('li')
      li.innerHTML = `<strong>${ing.nom}</strong> · ${ing.quantite_g}g (${ing.certitude})`
      ul.appendChild(li)
    })
    section.appendChild(ul)

    const hr = document.createElement('hr')
    hr.style.margin='16px 0'
    section.appendChild(hr)

    // Suggestions (max 6)
    const sugg = document.createElement('h5')
    sugg.textContent = '🍲 Suggestions de recettes'
    sugg.style.marginBottom='10px'
    section.appendChild(sugg)

    const ulSugg = document.createElement('ul')
    ulSugg.style.listStyle='none'; ulSugg.style.padding=0
    const recs = data.suggestions_recettes||[]
    recs.slice(0, 6).forEach(r => {
      const li = document.createElement('li')
      li.innerHTML = `<a href='#' onclick='loadRecipe("${r.fichier.replace(/\./g,'\\.')}")' style='color:#1976d2;text-decoration:underline'>${r.titre} (${r.kcal_100g||0}kcal/100g)</a>`
      ulSugg.appendChild(li)
    })
    section.appendChild(ulSugg)

    result.appendChild(section)
  }
}

if (typeof document !== 'undefined') {
  console.log('[PlateAnalyzer] script loaded, readyState=', document.readyState)
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', PlateAnalyzer.init)
  } else {
    // Le DOM est déjà chargé (ex: script exécuté après DOMContentLoaded) -> init immédiat
    PlateAnalyzer.init()
  }
  console.log('[PlateAnalyzer] init attached/called, upload btn found=', !!document.getElementById(PlateAnalyzer.UPLOAD_BUTTON_ID))
}
