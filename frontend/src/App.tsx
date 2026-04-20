import { type FormEvent, useEffect, useState } from "react";

import { createProvider, getHealth, getProviders } from "./api";
import type { Provider, ProviderHealth } from "./api";

export default function App() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [health, setHealth] = useState<ProviderHealth[]>([]);
  const [name, setName] = useState("");
  const [exposedModel, setExposedModel] = useState("default");
  const [routePolicy, setRoutePolicy] = useState("http-first");
  const [httpBaseUrl, setHttpBaseUrl] = useState("");

  useEffect(() => {
    void Promise.all([getProviders(), getHealth()]).then(([providerRows, healthRows]) => {
      setProviders(providerRows);
      setHealth(healthRows);
    });
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const created = await createProvider({
      name,
      exposed_model: exposedModel,
      route_policy: routePolicy,
      http_enabled: true,
      cli_enabled: false,
      http_base_url: httpBaseUrl,
      http_headers_json: "{}",
      cli_args_json: "[]",
      cli_env_json: "{}",
    });
    setProviders((current) => current.concat(created));
    setName("");
    setHttpBaseUrl("");
  }

  return (
    <main style={{ fontFamily: "sans-serif", padding: 24 }}>
      <h1>AgentHub Admin</h1>

      <section>
        <h2>Providers</h2>
        <form onSubmit={handleSubmit}>
          <label>
            Provider Name
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            Exposed Model
            <input value={exposedModel} onChange={(event) => setExposedModel(event.target.value)} />
          </label>
          <label>
            Route Policy
            <select value={routePolicy} onChange={(event) => setRoutePolicy(event.target.value)}>
              <option value="http-first">http-first</option>
              <option value="cli-first">cli-first</option>
              <option value="fixed-http">fixed-http</option>
              <option value="fixed-cli">fixed-cli</option>
            </select>
          </label>
          <label>
            HTTP Base URL
            <input
              required
              value={httpBaseUrl}
              onChange={(event) => setHttpBaseUrl(event.target.value)}
            />
          </label>
          <button type="submit">Add Provider</button>
        </form>

        <ul>
          {providers.map((provider) => (
            <li key={provider.id}>
              {provider.name} - {provider.exposed_model} - {provider.route_policy}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>Health</h2>
        <ul>
          {health.map((item) => (
            <li key={item.name}>
              {item.name} - http:{String(item.capabilities.http)} - cli:{String(item.capabilities.cli)}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>Logs</h2>
        <p>Request logs land in the backend first. Keep the frontend read-only here until log pagination exists.</p>
      </section>
    </main>
  );
}
