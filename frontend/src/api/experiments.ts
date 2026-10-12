// Tipagem dos dados que vamos enviar para a API
export interface SweepRequest {
  model_type: string;
  base_params: Record<string, number>;
  sweep_variable: string;
  start: number;
  end: number;
  step: number;
}

// Tipagem de cada ponto que a API devolve
export interface SweepPoint {
  sweep_value: number;
  rho?: number;
  L?: number;
  Lq?: number;
  W?: number;
  Wq?: number;
  p0?: number;
  throughput?: number;
  p_wait?: number;
  p_block?: number;
  warning?: string;
}

// Tipagem da resposta completa
export interface SweepResponse {
  model_type: string;
  sweep_variable: string;
  points: SweepPoint[];
}

// Função que faz a requisição HTTP para o nosso novo endpoint
export async function runExperimentSweep(request: SweepRequest): Promise<SweepResponse> {
  // Ajuste a URL base se você usar alguma variável de ambiente ou Axios configurado
  const response = await fetch('/api/experiments/sweep', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Erro ao gerar curva de sensibilidade.');
  }

  return response.json();
}