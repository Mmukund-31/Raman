import Plotly from 'plotly.js-gl3d-dist-min'
import createPlotlyComponent from 'react-plotly.js/factory'

/** Plotly's WebGL bundle (scatter3d, surface); imported lazily so 2D-only pages never download it. */
const Plot3D = createPlotlyComponent(Plotly)
export default Plot3D
