// frontend/app/layout.tsx
export const metadata = {
  title: "PrintReady Vectorizer (MVP)",
  description: "First-party vectorizer demo",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "system-ui, Arial, sans-serif" }}>
        {children}
      </body>
    </html>
  );
}
