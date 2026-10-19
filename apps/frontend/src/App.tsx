import { BrowserRouter, Route, Routes } from "react-router";

import { Layout } from "./components/Layout";
import { ChatPage } from "./pages/ChatPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { LogoutPage } from "./pages/LogoutPage";
import { SignUpPage } from "./pages/SignUpPage";
import { UsersPage } from "./pages/UsersPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<HomePage />} />
          <Route path="signup" element={<SignUpPage />} />
          <Route path="login" element={<LoginPage />} />
          <Route path="logout" element={<LogoutPage />} />
          <Route path="users" element={<UsersPage />} />
          <Route path="documents" element={<DocumentsPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="chat/:conversationId" element={<ChatPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
