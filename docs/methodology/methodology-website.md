**Methodology Notes - Adam edit**

Peter Rayner

*\
*** &lt;METHODOLOGY OVERVIEW&gt;**

**Initial Emissions Estimates\
\
How do we estimate methane emissions?\
\
**Methane comes from many activities, and there is no single data source
which  reports how much comes from each activity in a
particular grid area, or grid cell. We need to calculate this by
adding up emissions from all the activities that occur in the grid
cell. There are two ways we can get this information. Sometimes,
especially for large emitters, they must report emissions. These are
captured in the National Greenhouse and Energy Report (NGER). These
are usually reported by each business. If the business has several
facilities we need some method to allocate the proportion of the
business's emissions coming from each facility and their locations.
Then we can add the emissions to the grid cell containing the
facility.  For other classes of emission we only have national totals.
We distribute the national total among grid cells according to how
much of the activity generating the emissions occurs there.\
\
The national estimate \[Australia's National Inventory of greenhouse gas
emissions is published on the Department of Climate Change
[*website*](https://www.dcceew.gov.au/climate-change/publications/national-inventory-reports)\]
for each activity is, itself, indirect. Instead we estimate or count the
amount of an activity taking place and multiply that by how much methane
is emitted by each unit of activity.\

+-----------------------------------------------------------------------+
| \                                                                     |
| This is described by the equation **E=fA**, where **E** is the        |
| emission, **A** is the amount of the activity and **f** is a factor   |
| relating to activities and emissions, called an ‘emission factor’.    |
+-----------------------------------------------------------------------+

Emission factors must be estimated or measured at one place and time,
then applied elsewhere. Incorrect emission factors will lead to
incorrect emission estimates. This is a major source of uncertainty in
methane emissions calculated in this way.\
\
\
**Using Surrogates to Estimate Spatial Distribution**

Sometimes we don’t have spatial data for the activity we want, but can
measure a good surrogate.\
\
For example, the amount of fossil fuel burnt in a region is calculated
by how much is sold to end-users. This can be established by sales
statistics which are often well known, but where people use the fossil
fuel is not.\
\
\[Previous research link\] has shown that fossil fuel use is predicted
well by the intensity of nighttime lights that are observed by
satellites. We can spatialise fossil fuel sources from different sectors
according to the intensity of nighttime lights.\

**Calculating Confidence in the Emissions Inventory**\
We need to calculate the level of confidence we have in the emissions
inventory. This informs the emissions update process (we will be more
likely to make corrections where we least trust the inventory), but also
helps us use the data to answer questions like the significance of
detected trends.\
\
Uncertainties in emissions come from uncertainties in activity data,
emission factors, regional totals, the data we use to spatialise them,
and the assumption that our spatial surrogate is accurate for the
emissions sector.\
\
Uncertainties in numbers like emission factors are particularly serious,
since they may bias emissions in a region rather than a single point.\
\
We usually express our confidence in an uncertainty, expressed as a
standard deviation $\sigma$. We calculate the uncertainty for each point in the
inventory by adding the uncertainties from each sector. For mathematical
reasons we add the squares
$\sigma = \sum_{i=1}^N \sigma_i^2$ where \$sigma_i$ is the
uncertainty for each sector.

\

**Atmospheric Pollution Model \
\
**Data flow begins with global weather observations. Most large weather
agencies generate short-term weather forecasts which they correct with
satellite and surface observations. This combination of forecast and
observation produces the best picture of wind, temperature and pressure
in the atmosphere we have. Agencies run these forecasts globally on a
mesh or a grid. The weather data is pixelated at the resolution of the
mesh, so the finer the mesh the better our data.\
\
Computational restrictions limit these global forecasts to about a 100km
mesh, which is not fine enough for our needs. Because of this, we run a
finer mesh weather model called the Weather Research and Forecast model
(WRF) in our region of interest.\
\
We need to know  about weather systems coming from outside the area of
our focus, so we use global weather models to feed information to the
edges of our region.\
\
**IMAGE: Map with a large mesh, with a finer mesh inset. Show a pressure
pattern pixelated at the two resolutions.**\
\
The WRF model produces a snapshot of pressure, wind, temperature and
moisture every few minutes. It is these wind patterns which move gases
like methane around in the atmosphere.\
\
Calculating a complete picture of the weather every few minutes is
extremely expensive. Moving gases around in the atmosphere is simpler;
we don’t need to calculate rainfall or thunderstorms, for example.
Because of this, we take the weather data from WRF and use it in an
air-pollution model, the Community Multi-Scale Air Quality Model
(CMAQ).\
\
CMAQ can also calculate how pollutants are formed and destroyed by
chemical processes in the atmosphere, though for our purposes these
processes are not very important.

**Expected Atmospheric Concentrations\
\
**By integrating our Initial Estimate with atmospheric pollution models,
we create a map indicating expected concentrations of methane.\
\
IMAGE\
\
This visualisation reflects the amount of methane contained in each
cubic metre of air across Australia, averaged through the atmosphere.\
\
\

**Satellite observations \
\
Overview**

\
\[IMAGE OF SATELLITE\]

**\
SCHEMATIC: Like the old slide deck, but we show there’s an atmosphere
and that we’re measuring through it. We could show some kind of plume at
the surface caused by an emission and show that we also see all this
pollutant higher in the atmosphere which obscures it.\
\
**Satellites measure light or infrared radiation (heat). When they view
the Earth, they see radiation that has passed through the atmosphere and
may have bounced off the surface.

Different gases in the atmosphere absorb different wavelengths (colours)
of light. So if we can measure the amount of light at different
wavelengths entering the atmosphere from the Sun, and can measure how
much makes it back out of the atmosphere towards the satellite, we can
calculate how much of the various gases occur in that atmosphere.

This is a complicated measurement for a number of reasons:

- Firstly, the light may not make it all the way to the surface. If it
bounces off a cloud, we may only measure the gas in part of the
atmosphere. We usually don’t know how high the cloud is, so we don’t
know how much of the atmosphere we’re measuring and can’t use these
measurements.\
\
- The light may pass through dust and smoke in the atmosphere. These
also affect the way light travels. While we can correct for small
amounts of these, if there is too much dust or smoke we cannot calculate
the gas amount.\
\
- The ground may also absorb different wavelengths differently. We can
correct for this provided that we know enough about the surface, but
this is not always true.\
\
- The use of sunlight means we can only measure during the day and can’t
measure too close to the poles in the winter.\
\
- If the Sun or the satellite are too low in the sky when viewed from
the place the light strikes the ground, then the light is weaker and
more likely to encounter clouds or dust. Measurements from S5P work best
in places with little cloud cover, not too close to the poles, and
without lots of dust pollution. Australia fits these criteria well.

**\
TROPOMI**

Open Methane uses measurements from the Tropospheric Monitoring
Instrument (TROPOMI) on board the Sentinel 5 Precursor (S5P) satellite.
The troposphere is the lowest 80% of the atmosphere.\
\
S5P orbits the Earth approximately every 100 minutes at a height of 824
kilometres. Its orbit is orientated almost North-South, and as such
passes near both poles. Its orbit is structured so that the satellite
stays fixed relative to the Sun, and the Earth rotates beneath it. This
is called a sun-synchronous orbit, which means S5P crosses the equator
at the same local time in every orbit, about 1:30PM travelling from
South to North, and 1:30AM when travelling from north to south.\
\
For half of each orbit, S5P is on the sunny side of the Earth and can
take measurements, while on the dark side it cannot. The length of the
orbit means there are about 14 orbits each day, but these deliberately
do not repeat but are interlaced. The orbits repeat in a 16-day cycle
with 227 distinct tracks. **there's probably an image for this**

\
IMAGE: A satellite grid over Earth, perhaps parallel lines with arrows
for direction, and grid lines across them for along-track sampling.

\
Detectors on satellites are similar to those found on digital cameras.
One difference is that instead of capturing an image like a camera does,
the satellite captures a single line, usually at right angles to the
direction the satellite is travelling. Also, like a digital camera, the
satellite takes time to capture enough light to produce useful data. All
this time the satellite is travelling over the Earth’s surface.\
\
Currently, the satellite travels 5.6km across the surface of the Earth
as it takes each measurement. Along the line of measurements
(perpendicular to the satellite’s path) the satellite designers must
decide how much to zoom or pan the instrument. A zoomed-in image will
have smaller pixels – and thus more detailed measurements – but with a
smaller area, leaving parts of the Earth that may never be measured.
If the satellite pans to a wider view it looks at lower angles to the
Earth's surface. this distorts the image with pixels at the edge being
larger than those near the centre. This is why the orbit does not
repeat every day. If it did, certain parts of the Earth would only
be seen in lower resolution. 
TROPOMI’s particular resolution and orbit mean that it potentially sees
every point on the globe once per day but the resolution will change
from day to day. \
\

IMAGE: PREVIOUS IMAGE BUT WITH CLOUD MASK, WITH MANY GRID CELLS BLANKED
OUT

\
**Impact of Clouds**

**\
**Earth is, on average, about 50% covered by cloud at any given time.
Due to the impact of cloud cover on visibility, TROPOMI cannot make
methane measurements for Open Methane in cloudy locations. This is
particularly troublesome in some regions such as the tropics in the wet
season, where it can stay cloudy for long periods.\
\
Clouds are also generally not continuous, so TROPOMI can make patchy
measurements through breaks in cloud cover. One trade-off of SP5’s orbit
and optical design is that TROPOMI often looks well off to the side of
its orbital track to make a measurement. These measurements are at high
light angles, so the chance of being intercepted by a cloud is
increased. TROPOMI also cannot make a measurement when there is too much
smoke or dust in the atmosphere.\
\
TROPOMI also cannot make many measurements over water. For these reasons
only a few percent of the total TROPOMI measurements are available, but
this still leaves about 50,000 measurements available over Australia each
day.\

**Detecting Plumes\
\
**When a pollutant like methane enters the atmosphere, it usually
spreads horizontally and vertically in a characteristic plume.

\
**FIGURE?**\
\
A methane plume will gradually mix with plumes from other sources and
the background of methane already in the atmosphere. Thus we would like
to identify each plume at its most concentrated and distinct. Satellite
instruments are good at this because they observe so many locations, but
they suffer from measuring methane through the whole atmosphere. Thus
even when measuring near the source of the plume it is diluted by the
background of methane already present.

\
Dealing with Uncertainty

Every measurement is uncertain. This is particularly clear with
satellites where what they measure (radiation arriving at their
detectors) is not what they wish to infer (e.g. methane concentration in
the atmosphere several hundreds of kilometres beneath them). However, we
can use an algorithm to link the two. This algorithm is based on
well-understood physics, but, as already mentioned, other aspects of the
atmosphere and surface can affect the satellite measurements.\
\
The algorithm that calculates methane concentration also calculates an
uncertainty on that measurement. We check both the measurements with a
network of ground stations which can themselves be checked against
absolute standards. This traceability of measurements to absolute
standards is critical for confidence in detection, and for being able to
use multiple different instruments.

**\
Generating Alerts **

\
Open Methane publishes notifications when measured methane
concentrations are significantly different from what is expected. We
calculate the expected value by combining our emissions inventory with
the air pollution model. This creates a forecast of the expected methane
concentration for every hour of every day.\
\
By carefully sampling the model forecast in exactly the same way as the
satellite samples the atmosphere, we can compare our expected value with
what we measure. We can only do this where the satellite makes an
observation, so much of Australia will be unavailable on a single day.
It’s important to remember that absence of data does not imply support
for the emissions inventory, simply that we cannot observe it.\
\
Care is also needed when deciding what is a significant difference
between expected and measured values. Concentrations vary naturally as
winds move methane from different sources around in the atmosphere. In
principle, we can predict all these variations with CMAQ, but no model
is perfect, so we will certainly fail to capture some variations.  These variations will be larger near strong sources of methane. Similarly, there is an uncertainty in the satellite measurements, so we apply a significance threshold for events:\
\[\|\mbox{expected} -\mbox{observed}\| > 2\sigma\].
\(\sigma\), our total uncertainty comprises the natural variation and
satellite uncertainty:
\[\sigma = [\sigma_v^2 +\sigma_s^2]^{0.5}\] where \(\sigma_v\) is the
uncertainty due to natural variation and \(\sigma_s\) is the
uncertainty due to satellite measurements. This threshold will be refined with experience. We also cross-check
significant uncertainties for potential problems with the satellite data
such as incorrect environmental factors.

There is a difference between the resolution of the concentration map
produced by CMAQ (25 x 25km) and the satellite observations (5.6 x
7.2km at best). This means we may see concentration events occurring at a
particular part of a model pixel due to the location of an emission
within the pixel. This is both useful and problematic. It is useful
because it can give guidance on where to look for the source of an
event. It is problematic because CMAQ can only relate average emissions
in pixels to average concentration in pixels.

If we measure an uneven distribution of satellite pixels within a CMAQ
pixel, we could bias this average. This is a serious problem with
networks of fixed stations, but we also need to account for it in
satellite data. We include this as an extra uncertainty in how well we
expect our model concentrations to match the satellite data.

Emissions Correction

Once we have accounted for possible uncertainties in the satellite data
and the capability of our models, we assume that other mismatches
between expected and observed concentrations are caused by errors in our
emissions inventory. Our task is to work backwards from the
concentration mismatches to work out where and how much to correct the
emissions. We do this by effectively running the atmospheric pollution
model backwards.

Remember that the satellite measures through the whole atmosphere and
that the wind distributes methane from an emission in three dimensions.
Thus we need to backtrack concentration differences through the
atmosphere, not just at the surface.

IMAGE: Show difference plot from alerts step and wind map with arrows
reversed

By applying these corrections from all concentration mismatches
together, and accounting for all the changes in wind direction over a
month, we can produce a corrected map of the emissions inventory.\
**IMAGE: Arrows leading backwards from high differences to show
increased emissions **

A single incorrect emission will hopefully generate several
concentration mismatches so that we have multiple cross-checks on the
location and size of any error. However the challenges presented by
clouds and dust, as discussed earlier, may mask certain erroneous
emissions, lacking the necessary satellite observations to identify
these errors.

Much like the events we’ve previously addressed, the absence of
correction to an emission could either suggest that the satellite
observations confirm the emissions inventory, or indicate that we lack
the necessary observations to verify it.

This uncertainty can be addressed through a series of hypothetical
scenarios. By randomly adjusting emissions and calculating the expected
concentrations that the satellite would observe, we can assess the
sensitivity of our model. If these hypothetical adjustments in emissions
result in significant differences in the calculated concentrations, it
gives us confidence that actual discrepancies would also be detected by
the satellite.

Conversely, if changes in emissions don’t result in noticeable
differences in modelled concentrations – typically due to cloud
interference – then we cannot place as much confidence in our updates to
the emissions inventory for that particular region.
