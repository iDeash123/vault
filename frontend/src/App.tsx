import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { LoginPage } from "./domains/auth/LoginPage";
import { OAuthCallbackPage } from "./domains/auth/OAuthCallbackPage";
import { RegisterPage } from "./domains/auth/RegisterPage";
import { CatalogPage } from "./domains/catalog/CatalogPage";
import { CreateLotPage } from "./domains/lot-create/CreateLotPage";
import { KitchenSinkPage } from "./domains/kitchen-sink/KitchenSinkPage";
import { AppShell } from "./domains/layout/AppShell";
import { LiveLotPage } from "./domains/live-auction/LiveLotPage";
import { WalletPage } from "./domains/wallet/WalletPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
});

export const AppRoutes: React.FC = () => {
  return (
    <AppShell>
      <Routes>
        <Route path="/catalog" element={<CatalogPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/auth/callback" element={<OAuthCallbackPage />} />
        <Route path="/wallet" element={<WalletPage />} />
        <Route path="/lots/new" element={<CreateLotPage />} />
        <Route path="/lots/:lotId" element={<LiveLotPage />} />
        <Route path="/kitchen-sink" element={<KitchenSinkPage />} />
        <Route path="/" element={<Navigate to="/catalog" replace />} />
        <Route path="*" element={<Navigate to="/catalog" replace />} />
      </Routes>
    </AppShell>
  );
};

export const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  );
};

export default App;
