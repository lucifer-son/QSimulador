import { useState } from 'react';
import Plot from 'react-plotly.js';
import { runExperimentSweep } from '../api/experiments';
import type { SweepRequest, SweepResponse } from '../api/experiments';
import { useThemeColors } from '../hooks/useThemeColors';

interface ExperimentTabProps {
  currentModel: string;
  baseParams: Record<string, number>;
}

export function ExperimentTab({ currentModel, baseParams }: ExperimentTabProps) {
  const colors = useThemeColors();
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
    padding: '0.6rem 0.8rem',
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
    marginBottom: '0.4rem',
    fontWeight: '500'
  };
  const unit = sweepVar === 'servers' ? '(unid.)' : '(req/s)';

  return (
    <div style={{ padding: '2rem' }}>
      
      {/* Cabeçalho e Painel de Contexto */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem', marginBottom: '2rem' }}>
        <div>
          <h2 className="experiment-title" style={{ margin: '0 0 0.5rem 0', fontSize: '1.5rem' }}>Análise de Sensibilidade</h2>
          <p className="experiment-muted" style={{ margin: 0 }}>Gere curvas de desempenho variando um parâmetro do sistema.</p>
        </div>
        
        {/* Este painel mostra os valores que NÃO estão a variar */}
        <div className="experiment-fixed" style={{ padding: '1rem 1.5rem' }}>
          <div className="experiment-fixed-label" style={{ fontSize: '0.8rem', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
            Parâmetros Fixos ({currentModel.toUpperCase()})
          </div>
          <div className="experiment-fixed-values" style={{ display: 'flex', gap: '1.5rem', fontSize: '1.1rem', fontWeight: 'bold' }}>
            {sweepVar !== 'lambda' && <span>λ = {baseParams.lambda}</span>}
            {sweepVar !== 'mu' && <span>μ = {baseParams.mu}</span>}
            {currentModel.includes('c') && sweepVar !== 'servers' && <span>c = {baseParams.servers}</span>}
            {currentModel.includes('k') && <span>K = {baseParams.capacity}</span>}
          </div>
        </div>
      </div>
      
      {/* Caixa do Painel de Controlo */}
      <div className="experiment-controls" style={{ padding: '1.5rem', display: 'flex', gap: '1.5rem', alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: '2rem' }}>
        <div>
          <label className="experiment-muted" style={labelStyle}>O que deseja variar?</label>
          <select className="experiment-input" style={selectStyle} value={sweepVar} onChange={e => setSweepVar(e.target.value)}>
            <option value="lambda">Taxa de Chegada (λ)</option>
            <option value="mu">Taxa de Serviço (μ)</option>
            {currentModel.includes('c') && <option value="servers">Nº de Servidores (c)</option>}
          </select>
        </div>
        
        <div>
          <label className="experiment-muted" style={labelStyle}>Início {unit}</label>
          <input className="experiment-input" style={inputStyle} type="number" value={start} onChange={e => setStart(e.target.value)} />
        </div>
        
        <div>
          <label className="experiment-muted" style={labelStyle}>Fim {unit}</label>
          <input className="experiment-input" style={inputStyle} type="number" value={end} onChange={e => setEnd(e.target.value)} />
        </div>
        
        <div>
          <label className="experiment-muted" style={labelStyle}>Passo {unit}</label>
          <input className="experiment-input" style={inputStyle} type="number" value={step} onChange={e => setStep(e.target.value)} />
        </div>
        
        <button 
          onClick={handleRunExperiment} 
          disabled={loading} 
          style={{ 
            padding: '0 1.5rem', 
            height: '42px',
            cursor: loading ? 'not-allowed' : 'pointer',
            backgroundColor: 'var(--accent)',
            color: 'var(--on-accent)',
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
        <div className="experiment-error">
          {error}
        </div>
      )}

      {result && result.points.some(p => p.warning) && (
        <div className="experiment-warning">
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
                marker: { color: colors.danger, size: 6 },
                line: { width: 3 },
                name: 'Tempo Médio no Sistema (W)'
              },
              {
                x: validPoints.map(p => p.sweep_value),
                y: validPoints.map(p => p.rho),
                type: 'scatter',
                mode: 'lines',
                line: { dash: 'dash', color: colors.accent, width: 2 },
                name: 'Utilização (ρ) [Eixo Direito]',
                yaxis: 'y2'
              }
            ]}
            layout={{
              title: `Comportamento do Sistema variando ${sweepVar === 'lambda' ? 'Taxa de Chegada' : sweepVar === 'mu' ? 'Taxa de Serviço' : 'Servidores'}`,
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { color: colors.text, family: 'inherit' },
              xaxis: { 
                title: `Valor de ${sweepVar}`, 
                gridcolor: colors.border,
                zerolinecolor: colors.border
              },
              yaxis: { 
                title: 'Tempo no Sistema (W)', 
                titlefont: {color: colors.danger},
                tickfont: {color: colors.danger},
                gridcolor: colors.border,
                zerolinecolor: colors.border
              },
              yaxis2: {
                title: 'Utilização (ρ)',
                titlefont: {color: colors.accent},
                tickfont: {color: colors.accent},
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