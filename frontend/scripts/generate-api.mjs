const schemaUrl = process.env.API_SCHEMA_URL ?? "http://localhost:8000/api/schema/?format=json";
const response = await fetch(schemaUrl);
if (!response.ok) {
  console.error(`No se pudo leer el esquema OpenAPI (${response.status}) en ${schemaUrl}.`);
  process.exit(1);
}
const schema = await response.text();
const { writeFileSync } = await import("node:fs");
const { execSync } = await import("node:child_process");
writeFileSync(new URL("../openapi.json", import.meta.url), schema);
execSync("npx openapi-typescript openapi.json -o src/api/schema.d.ts", { stdio: "inherit" });
console.log(
  "Esquema escrito en src/api/schema.d.ts. El cliente del panel vive en src/api/types.ts.",
);
