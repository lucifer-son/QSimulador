import { useState } from 'react';
import Plot from 'react-plotly.js';
import { runExperimentSweep } from '../api/experiments';
import type { SweepRequest, SweepResponse } from '../api/experiments';

interface ExperimentTabProps {
  currentModel: string;
  baseParams: Record<string, number>;
}

export function ExperimentTab({ currentModel, baseParams }: ExperimentTabProps) {
  const [sweepVar, setSweepVar] = useState('lambda');
  const [start, setStart] = useState<number | string>(10);
  const [end, setEnd] = useState<number | string>(50);
  const [step, setStep] = useState<number | string>(5);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SweepResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleRunExperiment = async () => {
    setLoading(true);
    setError(null);
    try {
      const req: SweepRequest = {
        model_type: currentModel.replace(/\//g, '').toLowerCase(),
        base_params: baseParams,
        sweep_variable: sweepVar,
        start: Number(start),
        end: Number(end),
        step: Number(step),
      };
      
      const data = await runExperimentSweep(req);
      setResult(data);
    } catch (err: any) {
      setError(err.message || 'Erro ao executar experimento.');
    } finally {
      setLoading(false);
    }
  };

 // Filtra os pontos inválidos para o gráfico não "cair para zero" no final
  const validPoints = result ? result.points.filter(p => p.W !== null) : [];

  // Estilos melhorados e mais espaçosos
  const inputStyle = {
    backgroundColor: '#1a1a1a',
    border: '1px solid #444',
    color: '#e0e0e0',
    padding: '0.6rem 0.8rem',
    borderRadius: '6px',
    outline: 'none',
    width: '130px',
    fontSize: '0.95rem'
  };

  const selectStyle = {
    ...inputStyle,
    width: '220px', // Largo o suficiente para o texto completo
    cursor: 'pointer'
  };

  const labelStyle = {
    display: 'block',
    fontSize: '0.85rem',
    color: '#aaa',
    marginBottom: '0.4rem',
    fontWeight: '500'
  };
  const unit = sweepVar === 'servers' ? '(unid.)' : '(req/s)';

  return (
    <div style={{ padding: '2rem' }}>
      
      {/* Cabeçalho e Painel de Contexto */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem', marginBottom: '2rem' }}>
        <div>
          <h2 style={{ margin: '0 0 0.5rem 0', fontSize: '1.5rem', color: '#fff' }}>Análise de Sensibilidade</h2>
          <p style={{ color: '#aaa', margin: 0 }}>Gere curvas de desempenho variando um parâmetro do sistema.</p>
        </div>
        
        {/* Este painel mostra os valores que NÃO estão a variar */}
        <div style={{ backgroundColor: '#1a1a1a', padding: '1rem 1.5rem', borderRadius: '8px', border: '1px solid #333' }}>
          <div style={{ fontSize: '0.8rem', color: '#888', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
            Parâmetros Fixos ({currentModel.toUpperCase()})
          </div>
          <div style={{ display: 'flex', gap: '1.5rem', fontSize: '1.1rem', fontWeight: 'bold', color: '#4a90e2' }}>
            {sweepVar !== 'lambda' && <span>λ = {baseParams.lambda}</span>}
            {sweepVar !== 'mu' && <span>μ = {baseParams.mu}</span>}
            {currentModel.includes('c') && sweepVar !== 'servers' && <span>c = {baseParams.servers}</span>}
            {currentModel.includes('k') && <span>K = {baseParams.capacity}</span>}
          </div>
        </div>
      </div>
      
      {/* Caixa do Painel de Controlo */}
      <div style={{ backgroundColor: '#242424', padding: '1.5rem', borderRadius: '8px', border: '1px solid #333', display: 'flex', gap: '1.5rem', alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: '2rem' }}>
        <div>
          <label style={labelStyle}>O que deseja variar?</label>
          <select style={selectStyle} value={sweepVar} onChange={e => setSweepVar(e.target.value)}>
            <option value="lambda">Taxa de Chegada (λ)</option>
            <option value="mu">Taxa de Serviço (μ)</option>
            {currentModel.includes('c') && <option value="servers">Nº de Servidores (c)</option>}
          </select>
        </div>
        
        <div>
          <label style={labelStyle}>Início {unit}</label>
          <input style={inputStyle} type="number" value={start} onChange={e => setStart(e.target.value)} />
        </div>
        
        <div>
          <label style={labelStyle}>Fim {unit}</label>
          <input style={inputStyle} type="number" value={end} onChange={e => setEnd(e.target.value)} />
        </div>
        
        <div>
          <label style={labelStyle}>Passo {unit}</label>
          <input style={inputStyle} type="number" value={step} onChange={e => setStep(e.target.value)} />
        </div>
        
        <button 
          onClick={handleRunExperiment} 
          disabled={loading} 
          style={{ 
            padding: '0 1.5rem', 
            height: '42px',
            cursor: loading ? 'not-allowed' : 'pointer',
            backgroundColor: '#4a90e2',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            fontWeight: 'bold',
            fontSize: '1rem'
          }}
        >
          {loading ? 'A calcular...' : 'Gerar Curva'}
        </button>
      </div>

      {error && (
        <div style={{ color: '#ff6b6b', marginBottom: '2rem', padding: '1rem', backgroundColor: 'rgba(255, 107, 107, 0.1)', border: '1px solid #ff6b6b', borderRadius: '6px' }}>
          {error}
        </div>
      )}

      {result && result.points.some(p => p.warning) && (
        <div style={{ color: '#ffcc00', marginBottom: '2rem', padding: '1rem', backgroundColor: 'rgba(255, 204, 0, 0.1)', border: '1px solid #ffcc00', borderRadius: '6px' }}>
          <strong>Aviso:</strong> O sistema atingiu instabilidade (demanda supera a capacidade) nos valores mais altos. Esses pontos foram omitidos do gráfico.
        </div>
      )}

      {validPoints.length > 0 && (
        <div style={{ marginTop: '1rem' }}>
          <Plot
            data={[
              {
                x: validPoints.map(p => p.sweep_value),
                y: validPoints.map(p => p.W),
                type: 'scatter',
                mode: 'lines+markers',
                marker: { color: '#ff4757', size: 6 },
                line: { width: 3 },
                name: 'Tempo Médio no Sistema (W)'
              },
              {
                x: validPoints.map(p => p.sweep_value),
                y: validPoints.map(p => p.rho),
                type: 'scatter',
                mode: 'lines',
                line: { dash: 'dash', color: '#4a90e2', width: 2 },
                name: 'Utilização (ρ) [Eixo Direito]',
                yaxis: 'y2'
              }
            ]}
            layout={{
              title: `Comportamento do Sistema variando ${sweepVar === 'lambda' ? 'Taxa de Chegada' : sweepVar === 'mu' ? 'Taxa de Serviço' : 'Servidores'}`,
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { color: '#e0e0e0', family: 'inherit' },
              xaxis: { 
                title: `Valor de ${sweepVar}`, 
                gridcolor: '#333',
                zerolinecolor: '#555'
              },
              yaxis: { 
                title: 'Tempo no Sistema (W)', 
                titlefont: {color: '#ff4757'}, 
                tickfont: {color: '#ff4757'},
                gridcolor: '#333',
                zerolinecolor: '#555'
              },
              yaxis2: {
                title: 'Utilização (ρ)',
                titlefont: {color: '#4a90e2'},
                tickfont: {color: '#4a90e2'},
                overlaying: 'y',
                side: 'right',
                range: [0, 1]
              },
              autosize: true,
              legend: { orientation: 'h', y: -0.2 }
            }}
            style={{ width: '100%', height: '450px' }}
          />
        </div>
      )}
    </div>
  );
}