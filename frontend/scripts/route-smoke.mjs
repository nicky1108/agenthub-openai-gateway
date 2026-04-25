const baseUrl = process.argv[2] ?? "http://127.0.0.1:3002";
const routes = ["/", "/docs", "/portal", "/portal/models", "/portal/providers", "/portal/api-keys"];

let failed = false;

for (const route of routes) {
  const url = new URL(route, baseUrl);
  try {
    const response = await fetch(url);
    const body = await response.text();
    const contentType = response.headers.get("content-type") ?? "";
    const ok =
      response.status === 200 &&
      contentType.includes("text/html") &&
      body.includes("<div id=\"root\">");

    if (!ok) {
      failed = true;
      console.error(`FAIL ${route}: status=${response.status} content-type=${contentType}`);
      continue;
    }
    console.log(`OK ${route}`);
  } catch (error) {
    failed = true;
    console.error(`FAIL ${route}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

if (failed) {
  process.exit(1);
}
