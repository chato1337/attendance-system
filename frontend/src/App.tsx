import { APP_SUMMARY, APP_TITLE } from "@/content";

export function App() {
  return (
    <main>
      <p className="eyebrow">Attendance System</p>
      <h1>{APP_TITLE}</h1>
      <p>{APP_SUMMARY}</p>
      <ul>
        <li>
          <a href="http://localhost:8000/api/schema/swagger-ui/">Documentación de la API</a>
        </li>
        <li>
          <a href="http://localhost:8000/api/v1/health/">Estado del servicio</a>
        </li>
      </ul>
    </main>
  );
}
