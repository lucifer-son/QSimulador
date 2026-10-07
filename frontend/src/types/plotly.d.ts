declare module "plotly.js-basic-dist-min" {
  interface PlotlyStatic {
    react(root: HTMLElement, data: unknown[], layout?: object, config?: object): Promise<unknown>;
    purge(root: HTMLElement): void;
  }
  const Plotly: PlotlyStatic;
  export default Plotly;
}
