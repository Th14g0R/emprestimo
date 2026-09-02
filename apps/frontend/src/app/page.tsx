export default function Home() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-slate-900 dark:to-slate-800 p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-2">
          Sistema de Controle de Empréstimos e Cartão
        </h1>
        <p className="text-xl text-gray-600 dark:text-gray-300 mb-8">
          Bem-vindo ao sistema de gestão de empréstimos pessoais
        </p>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Placeholder cards */}
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
              Dashboard
            </h2>
            <p className="text-gray-600 dark:text-gray-400">
              Visualize seus empréstimos e saldo em tempo real
            </p>
          </div>
          
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
              Clientes
            </h2>
            <p className="text-gray-600 dark:text-gray-400">
              Gerencie todos os seus clientes e empréstimos
            </p>
          </div>
          
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
              Relatórios
            </h2>
            <p className="text-gray-600 dark:text-gray-400">
              Exporte dados em PDF e Excel
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}
