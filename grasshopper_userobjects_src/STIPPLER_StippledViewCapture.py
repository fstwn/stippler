#! python3
# -*- coding: utf-8 -*-
# venv: STIPPLER
print('ENV OK!')
# r: charset_normalizer
# r: git+https://github.com/fstwn/stippler.git@python39-rhino-port#subdirectory=code


# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import os  # NOQA
import datetime  # NOQA

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # NOQA
import Rhino  # NOQA
import Grasshopper  # NOQA
import scriptcontext as sc  # NOQA

from stippler import (  # NOQA
    IllustrationParams,
    stipple,
    render_matplotlib,
    render_svg,
)

OUTPUT_FORMATS = {
    0: '.png',
    1: '.svg',
    2: '.pdf',
}

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'StippledViewCapture'  # NOQA
ghenv.Component.NickName = 'StippledViewCapture'  # NOQA
ghenv.Component.Category = 'STIPPLER'  # NOQA
ghenv.Component.SubCategory = '1 Stippled Visualization'  # NOQA
ghenv.Component.Description = (  # NOQA
    'Captures the active Rhino viewport to PNG, then runs the stippler '
    'pipeline and writes a second file with the _stippled suffix. Supports '
    'PNG, SVG, and PDF stipple output, capture dimensions, background color, '
    'viewport visibility options, hand-drawn stippling controls, and '
    'optional Lu et al. scientific-illustration enhancements. Depth and '
    'normal auxiliary maps are captured automatically when the options that '
    'need them are enabled.'
)


class StippledViewCapture(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 260630
    """

    def __init__(self):
        super().__init__()
        self.Component = ghenv.Component  # NOQA
        self.InputParams = self.Component.Params.Input
        self.OutputParams = self.Component.Params.Output

    def _addRemark(self, msg: str = ''):
        """Add a remark message to the component runtime messages."""
        rml = self.Component.RuntimeMessageLevel.Remark
        self.AddRuntimeMessage(rml, msg)

    def _addWarning(self, msg: str = ''):
        """Add a warning message to the component runtime messages."""
        rml = self.Component.RuntimeMessageLevel.Warning
        self.AddRuntimeMessage(rml, msg)

    def _addError(self, msg: str = ''):
        """Add an error message to the component runtime messages."""
        rml = self.Component.RuntimeMessageLevel.Error
        self.AddRuntimeMessage(rml, msg)

    def _colorToHex(self, color):
        if color is None:
            return 'white'
        return '#%02x%02x%02x' % (color.R, color.G, color.B)

    def _resolveOptionalPath(self, path):
        if path is None:
            return None
        text = str(path).strip()
        if not text:
            return None
        return text

    def _needsDepthCapture(self, depth_attenuation, depth_override):
        return bool(depth_attenuation) and not depth_override

    def _needsNormalCapture(self, silhouette_density, lighting,
                            silhouette_curves, normal_override):
        if normal_override:
            return False
        return bool(silhouette_density or lighting or silhouette_curves)

    def _viewDirectionFromActiveView(self):
        """Return unit camera-to-target direction as (x, y, z)."""
        sc.escape_test()
        sc.doc = Rhino.RhinoDoc.ActiveDoc
        view = sc.doc.Views.ActiveView
        ghdoc = self.Component.OnPingDocument()
        sc.doc = ghdoc  # NOQA
        if view is None:
            return (0.0, 0.0, 1.0)
        camera = view.ActiveViewport.CameraLocation
        target = view.ActiveViewport.CameraTarget
        direction = target - camera
        if direction.IsTiny:
            direction = view.ActiveViewport.CameraZ
        direction.Unitize()
        return (direction.X, direction.Y, direction.Z)

    def _vector3dToTuple(self, vector, default=(1.0, 1.0, 1.0)):
        if vector is None:
            return default
        length = vector.Length
        if length < 1e-12:
            return default
        return (vector.X / length, vector.Y / length, vector.Z / length)

    def _buildIllustrationParams(
            self,
            boundary,
            silhouette_density,
            interior,
            lighting,
            depth,
            gradient_size,
            silhouette_curves,
            light_dir,
            view_dir,
            curve_width):
        return IllustrationParams(
            boundary=bool(boundary),
            silhouette_density=bool(silhouette_density),
            interior=bool(interior),
            lighting=bool(lighting),
            depth=bool(depth),
            gradient_size=bool(gradient_size),
            silhouette_curves=bool(silhouette_curves),
            light=light_dir,
            view=view_dir,
        ), curve_width

    def checkOrMakeFolder(self):
        """
        Check/makes a "Captures" folder in the GH def folder and a subfolder
        in the format 'YYMMDD'.
        """
        sc.escape_test()
        ghdoc = self.Component.OnPingDocument()
        date = datetime.date.today()
        yy = str(date.year)[-2:]
        mm = str(date.month).zfill(2)
        dd = str(date.day).zfill(2)
        timestamp = yy + mm + dd
        docpath = ghdoc.FilePath  # NOQA
        if docpath:
            folder = os.path.dirname(docpath)
            captureFolder = folder + "\\Captures\\" + timestamp
            if not os.path.isdir(captureFolder):
                os.makedirs(captureFolder)
            return captureFolder

    def makeFileName(self):
        """ Make a string with the gh def name + current hourMinuteSecond """
        n = datetime.datetime.now()
        ho, mt, sec = str(n.hour), str(n.minute), str(n.second)
        if len(ho) == 1:
            ho = "0" + ho
        if len(mt) == 1:
            mt = "0" + mt
        if len(sec) == 1:
            sec = "0" + sec
        hms = ho + mt + sec
        ghdoc = self.Component.OnPingDocument()
        ghDef = ghdoc.DisplayName.strip('*')
        return ghDef + '_' + hms

    def _resolveOutputFormat(self, format_code):
        if format_code is None:
            format_code = 0
        ext = OUTPUT_FORMATS.get(int(format_code))
        if ext is None:
            raise Exception(
                'OutputFormat must be 0 (PNG), 1 (SVG), or 2 (PDF).'
            )
        return ext

    def _viewCaptureBitmap(self, width, height, grid, world_axes, cplane_axes):
        """
        Capture the active Rhino view; caller must set sc.doc to RhinoDoc.
        """
        sc.escape_test()
        activeView = sc.doc.Views.ActiveView
        if activeView is None:
            raise Exception('No active Rhino viewport to capture.')
        viewcap = Rhino.Display.ViewCapture()
        viewcap.DrawGrid = grid
        viewcap.DrawGridAxes = world_axes
        viewcap.DrawAxes = cplane_axes
        viewcap.Height = height
        viewcap.Width = width
        bitmap = viewcap.CaptureToBitmap(activeView)
        if bitmap is None:
            raise Exception('ViewCapture returned an empty bitmap.')
        return bitmap

    def _saveBitmap(self, bitmap, path):
        bitmap.Save(path, System.Drawing.Imaging.ImageFormat.Png)

    def _captureWithToggleCommand(self, command, width, height, path):
        """
        Toggle a Rhino display command, ViewCapture, then toggle off.
        """
        sc.escape_test()
        ghdoc = self.Component.OnPingDocument()
        sc.doc = Rhino.RhinoDoc.ActiveDoc
        toggled_on = False
        try:
            if not Rhino.RhinoApp.RunScript(command, False):
                raise Exception('Rhino command failed: %s' % command)
            toggled_on = True
            bitmap = self._viewCaptureBitmap(
                width,
                height,
                False,
                False,
                False
            )
            self._saveBitmap(bitmap, path)
            Rhino.RhinoApp.WriteLine(path)
            return path
        finally:
            if toggled_on:
                Rhino.RhinoApp.RunScript(command, False)
            sc.doc = ghdoc  # NOQA

    def captureActiveViewToFile(
            self,
            width,
            height,
            path,
            grid,
            worldAxes,
            cplaneAxes):
        """Capture the shaded beauty pass."""
        sc.escape_test()
        ghdoc = self.Component.OnPingDocument()
        sc.doc = Rhino.RhinoDoc.ActiveDoc
        try:
            bitmap = self._viewCaptureBitmap(
                width, height, grid, worldAxes, cplaneAxes)
            self._saveBitmap(bitmap, path)
            Rhino.RhinoApp.WriteLine(path)
            sc.doc = ghdoc  # NOQA
            return path
        except Exception as e:
            sc.doc = ghdoc  # NOQA
            raise Exception(f'Capture failed, check the path: {str(e)}')

    def captureDepthMap(self, width, height, path):
        """Capture a grayscale depth map via ShowZBuffer + ViewCapture."""
        self._addRemark('Capturing depth map (ShowZBuffer)...')
        return self._captureWithToggleCommand(
            '_ShowZBuffer',
            width,
            height,
            path
        )

    def captureNormalMap(self, width, height, path):
        """Capture an RGB normal map via TestShowNormalMap + ViewCapture."""
        self._addRemark(
            'Capturing normal map (TestShowNormalMap). '
            'Monochrome or Arctic display mode works best.'
        )
        return self._captureWithToggleCommand(
            '_TestShowNormalMap', width, height, path)

    def stippleCapture(
            self,
            capture_path,
            output_path,
            output_ext,
            n_point,
            n_iter,
            gamma,
            r_min,
            r_max,
            size_jitter,
            position_jitter,
            edge_noise,
            seed,
            dpi,
            background,
            illustration,
            normal_map,
            depth_map,
            curve_width):
        """Run stippler on the capture and write the stippled output file."""
        sc.escape_test()
        result = stipple(
            capture_path,
            n_point=n_point,
            n_iter=n_iter,
            gamma=gamma,
            r_min=r_min,
            r_max=r_max,
            size_jitter=size_jitter,
            position_jitter=position_jitter,
            edge_noise=edge_noise,
            seed=seed,
            illustration=illustration,
            normal_map=normal_map,
            depth_map=depth_map,
        )
        if output_ext == '.svg':
            render_svg(
                result,
                output_path,
                background=background,
                curve_width=curve_width,
            )
        else:
            render_matplotlib(
                result,
                output_path,
                dpi=dpi,
                background=background,
                curve_width=curve_width,
            )
        return output_path, len(result.points), len(result.curves)

    def _setInputDescriptions(self):
        descriptions = [
            'Toggle to execute capture and stippling',
            'Open the stippled output file after creation',
            'Image width in pixels (default: 1920)',
            'Image height in pixels (default: 1080)',
            'Background color for the viewport capture and stipple output',
            'Show grid in the captured image',
            'Show world axes in the captured image',
            'Show construction plane axes in the captured image',
            'Stipple output format: 0=PNG (default), 1=SVG, 2=PDF',
            'Number of stipple dots (default: 5000)',
            ('Max Lloyd relaxation iterations; lower = '
             'looser spacing (default: 50)'),
            ('Density contrast curve; >1 concentrates '
             'dots in dark areas (default: 1.0)'),
            'Minimum dot radius in density-pixel units (default: 1.0)',
            'Maximum dot radius in density-pixel units (default: 1.0)',
            'Per-dot radius noise as a fraction, e.g. 0.15 (default: 0.0)',
            ('Gaussian positional noise std in '
             'density-pixel units (default: 0.0)'),
            ('Dot-edge wobble as a fraction of '
             'radius, e.g. 0.08 (default: 0.0)'),
            ('Random seed; 0 or less uses a '
             'non-deterministic seed (default: 0)'),
            'Raster output DPI for PNG/PDF stipple output (default: 300)',
            'Boost stipple density on high-gradient edges (Lu et al.)',
            'Boost density on silhouette regions; auto-captures normal map',
            'Sparse stipples in flat/low-gradient regions (Lu et al.)',
            'Modulate density from surface lighting; auto-captures normal map',
            'Attenuate far regions; auto-captures depth map (Lu et al.)',
            'Scale dot radius by local gradient magnitude (Lu et al.)',
            'Draw silhouette curves; auto-captures normal map when enabled',
            'Optional normal-map override path (skip auto-capture when set)',
            'Optional depth-map override path (skip auto-capture when set)',
            'Light direction for lighting enhancement (default: 1,1,1)',
            'Silhouette curve stroke width in output pixels (default: 0.6)',
        ]
        for index, text in enumerate(descriptions):
            if index < self.InputParams.Count:
                self.InputParams[index].Description = text

    def RunScript(self,
            Toggle: bool,
            OpenFile: bool,
            Width: int,
            Height: int,
            BackgroundColor: System.Drawing.Color,
            Grid: bool,
            WorldAxes: bool,
            CPlaneAxes: bool,
            OutputFormat: int,
            NumDots: int,
            Iterations: int,
            Gamma: float,
            RMin: float,
            RMax: float,
            SizeJitter: float,
            PositionJitter: float,
            EdgeNoise: float,
            Seed: int,
            Dpi: int,
            Boundary: bool,
            SilhouetteDensity: bool,
            Interior: bool,
            Lighting: bool,
            DepthAttenuation: bool,
            GradientSize: bool,
            SilhouetteCurves: bool,
            NormalMap: str,
            DepthMap: str,
            LightDir: Rhino.Geometry.Vector3d,
            CurveWidth: float):
        self._setInputDescriptions()
        self.OutputParams[0].Description = (
            'Path to the stippled output file (<name>_stippled.<ext>)'
        )
        if self.OutputParams.Count > 1:
            self.OutputParams[1].Description = (
                'Path to the original viewport capture PNG'
            )
        if self.OutputParams.Count > 2:
            self.OutputParams[2].Description = (
                'Path to the auto-captured normal map (<name>_normal.png), '
                'if created'
            )
        if self.OutputParams.Count > 3:
            self.OutputParams[3].Description = (
                'Path to the auto-captured depth map (<name>_depth.png), '
                'if created'
            )

        StippledPath = Grasshopper.DataTree[System.Object]()
        CapturePath = Grasshopper.DataTree[System.Object]()
        NormalPath = Grasshopper.DataTree[System.Object]()
        DepthPath = Grasshopper.DataTree[System.Object]()

        if not Toggle:
            self.Component.Message = (
                'Ready to capture view (toggle to execute)'
            )
            return StippledPath, CapturePath, NormalPath, DepthPath

        try:
            if BackgroundColor:
                settings = Rhino.ApplicationSettings.AppearanceSettings
                settings.ViewportBackgroundColor = BackgroundColor
                self._addRemark('Background color set for capture')

            if not Width:
                Width = 1920
            if not Height:
                Height = 1080
            if not NumDots:
                NumDots = 5000
            if not Iterations:
                Iterations = 50
            stipple_ext = self._resolveOutputFormat(OutputFormat)
            if Gamma is None:
                Gamma = 1.0
            if RMin is None:
                RMin = 1.0
            if RMax is None:
                RMax = 1.0
            if SizeJitter is None:
                SizeJitter = 0.0
            if PositionJitter is None:
                PositionJitter = 0.0
            if EdgeNoise is None:
                EdgeNoise = 0.0
            if not Dpi:
                Dpi = 300
            if CurveWidth is None or CurveWidth <= 0:
                CurveWidth = 0.6

            seed = Seed if Seed and Seed > 0 else None
            background = self._colorToHex(BackgroundColor)
            normal_map = self._resolveOptionalPath(NormalMap)
            depth_map = self._resolveOptionalPath(DepthMap)
            view_dir = self._viewDirectionFromActiveView()
            light_dir = self._vector3dToTuple(LightDir)

            capture_depth = self._needsDepthCapture(
                DepthAttenuation, depth_map)
            capture_normal = self._needsNormalCapture(
                SilhouetteDensity, Lighting, SilhouetteCurves, normal_map)

            illustration, curve_width = self._buildIllustrationParams(
                Boundary,
                SilhouetteDensity,
                Interior,
                Lighting,
                DepthAttenuation and (capture_depth or bool(depth_map)),
                GradientSize,
                SilhouetteCurves,
                light_dir,
                view_dir,
                CurveWidth,
            )

            self.Component.Message = 'Preparing capture...'

            capFolder = self.checkOrMakeFolder()
            if not capFolder:
                raise Exception(
                    'Save the Grasshopper definition first so a capture '
                    'folder can be created.'
                )

            fileName = self.makeFileName()
            capture_path = os.path.join(capFolder, fileName + '.png')
            depth_path = os.path.join(capFolder, fileName + '_depth.png')
            normal_path = os.path.join(capFolder, fileName + '_normal.png')
            stipple_path = os.path.join(
                capFolder, fileName + '_stippled' + stipple_ext
            )

            self.Component.Message = 'Capturing beauty pass...'
            captured_path = self.captureActiveViewToFile(
                Width, Height, capture_path, Grid, WorldAxes, CPlaneAxes
            )
            self._addRemark(f'Captured beauty pass to {captured_path}')

            if capture_depth:
                self.Component.Message = 'Capturing depth map...'
                depth_map = self.captureDepthMap(Width, Height, depth_path)
                self._addRemark(f'Captured depth map to {depth_map}')

            if capture_normal:
                self.Component.Message = 'Capturing normal map...'
                normal_map = self.captureNormalMap(Width, Height, normal_path)
                self._addRemark(f'Captured normal map to {normal_map}')

            self.Component.Message = 'Stippling...'
            output_path, dot_count, curve_count = self.stippleCapture(
                captured_path,
                stipple_path,
                stipple_ext,
                NumDots,
                Iterations,
                Gamma,
                RMin,
                RMax,
                SizeJitter,
                PositionJitter,
                EdgeNoise,
                seed,
                Dpi,
                background,
                illustration,
                normal_map,
                depth_map,
                curve_width,
            )
            self._addRemark(
                f'Stippled {dot_count} dots and {curve_count} curves to '
                f'{output_path}'
            )

            ghp = Grasshopper.Kernel.Data.GH_Path(0)
            StippledPath.Add(output_path, ghp)
            CapturePath.Add(captured_path, ghp)
            if normal_map:
                NormalPath.Add(normal_map, ghp)
            if depth_map:
                DepthPath.Add(depth_map, ghp)

            if OpenFile:
                os.startfile(output_path)
                self._addRemark('Stippled file opened')

            self.Component.Message = (
                f'Saved: {dot_count} dots, {curve_count} curves'
            )
            Rhino.RhinoApp.WriteLine(captured_path)
            if depth_map:
                Rhino.RhinoApp.WriteLine(depth_map)
            if normal_map:
                Rhino.RhinoApp.WriteLine(normal_map)
            Rhino.RhinoApp.WriteLine(output_path)
            return StippledPath, CapturePath, NormalPath, DepthPath

        except Exception as e:
            msg = f'Capture/stipple failed: {str(e)}'
            self._addError(msg)
            self.Component.Message = msg
            return StippledPath, CapturePath, NormalPath, DepthPath
