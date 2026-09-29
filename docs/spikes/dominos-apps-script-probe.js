/**
 * Probe Mínimo para Google Apps Script — Domino's Pizza Portugal
 * 
 * Executa no ambiente serverless do Google Apps Script (IPs do Google Cloud ASN 15169).
 * Efetua GET à homepage oficial da Domino's para verificar se o Cloudflare Bot Fight Mode
 * permite o acesso a partir da infraestrutura da Google.
 * 
 * Regras Estritas:
 * - Não resolve CAPTCHA nem contorna WAF
 * - Não armazena cookies nem dados pessoais
 * - Devolve apenas metadados técnicos de conectividade
 */

function probeDominosHomepage() {
  const targetUrl = "https://www.dominospizza.pt/";

  const options = {
    method: "get",
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7"
    },
    muteHttpExceptions: true,
    followRedirects: true
  };

  try {
    const response = UrlFetchApp.fetch(targetUrl, options);
    const status = response.getResponseCode();
    const content = response.getContentText();
    const length = content.length;

    // Extração do <title>
    const titleMatch = content.match(/<title[^>]*>(.*?)<\/title>/i);
    const title = titleMatch ? titleMatch[1].trim() : "Sem título";

    // Presença dos seletores reais da Domino's
    const hasComboId = content.includes("combo-id");
    const hasOfferTitle = content.includes("offer-title");
    const hasCloudflareChallenge = status === 403 || content.includes("Just a moment...") || content.includes("cf-browser-verification");

    const result = {
      timestamp: new Date().toISOString(),
      url: targetUrl,
      status: status,
      length: length,
      title: title,
      hasComboId: hasComboId,
      hasOfferTitle: hasOfferTitle,
      hasCloudflareChallenge: hasCloudflareChallenge,
      verdict: hasComboId ? "SUCCESS_ACCESSIBLE" : (hasCloudflareChallenge ? "BLOCKED_CLOUDFLARE_403" : "UNKNOWN")
    };

    Logger.log("Resultado da Sonda Domino's: %s", JSON.stringify(result, null, 2));
    return result;

  } catch (error) {
    const errResult = {
      timestamp: new Date().toISOString(),
      url: targetUrl,
      error: error.toString(),
      verdict: "FETCH_ERROR"
    };
    Logger.log("Erro na execução da Sonda Domino's: %s", JSON.stringify(errResult, null, 2));
    return errResult;
  }
}

/**
 * Instruções para configurar Trigger Diário no Google Apps Script:
 * 
 * 1. Aceder a https://script.google.com/ e criar um novo projeto ("PizzaRadar-DominoSync").
 * 2. Colar este código no editor (Code.gs).
 * 3. Clicar no menu lateral "Triggers" (ícone do relógio) -> "Add Trigger".
 * 4. Configurar:
 *    - Function: probeDominosHomepage (ou a função de recolha e envio)
 *    - Event source: Time-driven
 *    - Type of based trigger: Day timer
 *    - Time of day: 10am to 11am (ou antes das refeições)
 * 5. Guardar.
 */
