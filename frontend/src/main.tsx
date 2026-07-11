import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { DemoProvider } from "./DemoContext";
import SiteAuth from "./SiteAuth";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
      throwOnError: false,
    },
    mutations: { throwOnError: false },
  },
});

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 40, maxWidth: 600 }}>
          <h1>SceneForge Studio</h1>
          <div className="card" style={{ borderColor: "var(--danger)" }}>
            <b>Something went wrong</b>
            <p className="muted">{this.state.error.message}</p>
            <button onClick={() => { this.setState({ error: null }); window.location.reload(); }}>
              reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <SiteAuth>
          <DemoProvider>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </DemoProvider>
        </SiteAuth>
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>,
);
