import axios, { AxiosInstance } from 'axios';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001/api';

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Add token to requests if available
    this.client.interceptors.request.use((config) => {
      const token = localStorage.getItem('token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });
  }

  // Clientes
  getClientes() {
    return this.client.get('/clientes');
  }

  getCliente(id: string) {
    return this.client.get(`/clientes/${id}`);
  }

  createCliente(data: any) {
    return this.client.post('/clientes', data);
  }

  updateCliente(id: string, data: any) {
    return this.client.patch(`/clientes/${id}`, data);
  }

  deleteCliente(id: string) {
    return this.client.delete(`/clientes/${id}`);
  }

  // Empréstimos
  getEmprestimos() {
    return this.client.get('/emprestimos');
  }

  getEmprestimo(id: string) {
    return this.client.get(`/emprestimos/${id}`);
  }

  createEmprestimo(data: any) {
    return this.client.post('/emprestimos', data);
  }

  updateEmprestimo(id: string, data: any) {
    return this.client.patch(`/emprestimos/${id}`, data);
  }

  // Dashboard
  getDashboard() {
    return this.client.get('/dashboard');
  }

  // Relatórios
  generateReport(data: any) {
    return this.client.post('/relatorios', data, {
      responseType: 'blob',
    });
  }
}

export const apiClient = new ApiClient();
