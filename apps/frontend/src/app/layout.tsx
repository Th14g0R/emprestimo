import type { Metadata } from 'next';
import { ThemeProvider } from '@/context/theme-context';
import './globals.css';

export const metadata: Metadata = {
  title: 'Sistema de Empréstimos',
  description: 'Gestão de empréstimos e cartão de crédito',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <body>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
