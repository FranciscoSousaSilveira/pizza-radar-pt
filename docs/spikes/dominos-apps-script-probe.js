/**
 * Sonda de Conectividade Google Apps Script — Domino's e Telepizza
 * 
 * Executa estritamente testes de conectividade HTTP com UrlFetchApp a partir
 * da rede da Google para validar se os WAFs das marcas permitem egress.
 * 
 * Regras Estritas:
 * - Zero escrita na base de dados
 * - Zero triggers nesta fase
 * - Zero tokens ou segredos
 * - Zero resolução de CAPTCHA ou bypass de WAF
 * - Devolve apenas estatísticas técnicas sanitizadas (nunca HTML ou cookies)
 */

function probeSources() {
  var targets = [
    { name: "Domino's Homepage", url: "https://www.dominospizza.pt/" },
    { name: "Telepizza App Promoções", url: "https://app.telepizza.pt/promocoes" },
    { name: "Telepizza Web Promoções", url: "https://www.telepizza.pt/promocoes" }
  ];

  var headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7"
  };

  var report = {
    executedAt: new Date().toISOString(),
    results: []
  };

  for (var i = 0; i < targets.length; i++) {
    var target = targets[i];
    var entry = {
      name: target.name,
      url: target.url,
      responseCode: null,
      contentLength: 0,
      title: "",
      hasComboId: false,
      comboIdCount: 0,
      hasViewPromotion: false,
      uniquePromotionIdsCount: 0,
      firstFiveIds: [],
      isCloudflareJustAMoment: false,
      error: null
    };

    try {
      var options = {
        method: "get",
        headers: headers,
        muteHttpExceptions: true,
        followRedirects: true
      };

      var response = UrlFetchApp.fetch(target.url, options);
      var code = response.getResponseCode();
      var content = response.getContentText() || "";

      entry.responseCode = code;
      entry.contentLength = content.length;

      // 1. Título HTML
      var titleMatch = content.match(/<title[^>]*>(.*?)<\/title>/i);
      entry.title = titleMatch ? titleMatch[1].replace(/\s+/g, " ").trim() : "Sem <title>";

      // 2. Deteção Cloudflare "Just a moment..."
      entry.isCloudflareJustAMoment = (
        code === 403 ||
        content.indexOf("Just a moment...") !== -1 ||
        content.indexOf("cf-browser-verification") !== -1 ||
        content.indexOf("challenge-running") !== -1
      );

      // 3. Seletores Domino's: combo-id
      var comboMatches = content.match(/combo-id=["']?([^"'\s>]+)/gi);
      if (comboMatches && comboMatches.length > 0) {
        entry.hasComboId = true;
        entry.comboIdCount = comboMatches.length;
        var comboIds = [];
        for (var c = 0; c < comboMatches.length; c++) {
          var idVal = comboMatches[c].replace(/combo-id=["']?/i, "").replace(/["']$/, "").trim();
          if (idVal && comboIds.indexOf(idVal) === -1) {
            comboIds.push(idVal);
          }
        }
        entry.firstFiveIds = comboIds.slice(0, 5);
      }

      // 4. Seletores Telepizza: view_promotion e promotion_id ou data-id
      entry.hasViewPromotion = content.indexOf("view_promotion") !== -1;

      var promoIdMatches = content.match(/promotion_id:\s*['"]([^'"]+)['"]/g);
      var dataIdMatches = content.match(/data-id=['"]([^'"]+)['"]/g);

      var teleIds = [];
      if (promoIdMatches) {
        for (var p = 0; p < promoIdMatches.length; p++) {
          var m = promoIdMatches[p].match(/promotion_id:\s*['"]([^'"]+)['"]/);
          if (m && m[1] && teleIds.indexOf(m[1]) === -1) {
            teleIds.push(m[1]);
          }
        }
      }
      if (dataIdMatches) {
        for (var d = 0; d < dataIdMatches.length; d++) {
          var dm = dataIdMatches[d].match(/data-id=['"]([^'"]+)['"]/);
          if (dm && dm[1] && teleIds.indexOf(dm[1]) === -1) {
            teleIds.push(dm[1]);
          }
        }
      }

      if (teleIds.length > 0) {
        entry.uniquePromotionIdsCount = teleIds.length;
        if (entry.firstFiveIds.length === 0) {
          entry.firstFiveIds = teleIds.slice(0, 5);
        }
      }

    } catch (err) {
      entry.error = err.toString();
    }

    report.results.push(entry);
  }

  var formattedJson = JSON.stringify(report, null, 2);
  Logger.log("\n" + formattedJson);
  return formattedJson;
}
