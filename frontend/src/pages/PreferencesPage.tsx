import { usePreferences } from "@/auth/preferences";
import { Field, Page } from "@/components/ui";
import { zoneOptions } from "@/lib/time";

export function PreferencesPage() {
  const theme = usePreferences((state) => state.theme);
  const timeZone = usePreferences((state) => state.timeZone);
  const setTheme = usePreferences((state) => state.setTheme);
  const setTimeZone = usePreferences((state) => state.setTimeZone);

  return (
    <Page
      title="Preferencias"
      lede="El tema y la zona horaria se guardan en este navegador. Los datos siguen en UTC."
    >
      <form className="form-grid card">
        <Field label="Tema">
          <select
            value={theme}
            onChange={(event) => setTheme(event.target.value as "light" | "dark")}
          >
            <option value="light">Claro</option>
            <option value="dark">Oscuro</option>
          </select>
        </Field>
        <Field label="Zona horaria de visualización">
          <select value={timeZone} onChange={(event) => setTimeZone(event.target.value)}>
            {zoneOptions(timeZone).map((zone) => (
              <option key={zone} value={zone}>
                {zone}
              </option>
            ))}
          </select>
        </Field>
      </form>
    </Page>
  );
}
