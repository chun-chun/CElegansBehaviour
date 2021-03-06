# -*- coding: utf-8 -*-
"""
Worm Geometry

collection of routines to detect, convert and manipulate worm shapes features

See also: 
  :mod:`model`
"""

__license__ = 'MIT License <http://www.opensource.org/licenses/mit-license.php>'
__author__ = 'Christoph Kirst <ckirst@rockefeller.edu>'
__docformat__ = 'rest'


import numpy as np
import matplotlib.pyplot as plt

import shapely.geometry as geom
from skimage.filters import threshold_otsu
from skimage.morphology import skeletonize

import scipy.ndimage.filters as filters
from scipy.interpolate import splev, splprep, UnivariateSpline
#from scipy.interpolate import splrep, dfitpack
from scipy.spatial import Voronoi

import cv2

from interpolation.spline import Spline
from interpolation.curve import Curve

from interpolation.resampling import resample as resample_curve
#from interpolation.intersections import curve_intersections_discrete;

from signalprocessing.peak_detection import find_peaks

from imageprocessing.contours import detect_contour, sort_points_to_line, inside_polygon;
from imageprocessing.skeleton_graph import skeleton_to_adjacency
  




##############################################################################
### Worm width profile

def default_width(npoints = 21):
  """Default width profile for a adult worm
  
  Arguments:
    npoints (int): number of sample points
    
  Returns:
    array: width profile
  
  Note: 
    This might need to be adjusted to data / age etc or directly detected from 
    images (see :func:`shape_from_image`).
  """
  def w(x):
    a = 9.56 * 0.5;
    b = 0.351;
    return a * np.power(x,b)*np.power(1-x, b) * np.power(0.5, -2*b);
  
  if npoints is None:
    return w;
  else:
    return w(np.linspace(0, 1, npoints));


##############################################################################
### Center Line Detection

def center_from_sides_vonroi(left, right, npoints = all, nsamples = all, resample = False, with_width = False, smooth = 0.1):
  """Finds mid line between the two side lines using Vonroi tesselation
  
  Arguments:
    left, right (nx2 array): vertices of the left and right curves
    npoints (int or all): number of points of the center line
    nsamples (int or all): number of sample points to construct center line
    resample (bool): force resampling of the side curves (e..g in case not uniformly sampled)
    with_width (bool): if True also return estimated width
    smooth (float): smoothing factor for final sampling
  
  Returns:
    nx2 array of midline vertices
  """
  # resample to same size
  nl = left.shape[0];
  nr = right.shape[0];
  if nsamples is all:
    nsamples = max(nl,nr);
  if npoints is all:
    npoints = max(nl,nr);
  
  if nsamples != nl or nsamples != nr or resample:
    leftcurve  = resample_curve(left, nsamples);
    rightcurve = resample_curve(right, nsamples);
  else:
    leftcurve = left;
    rightcurve = right;
  
  # vonroi tesselate 
  polygon = np.vstack([leftcurve, rightcurve[::-1]])
  vor = Voronoi(polygon)
  #voronoi_plot_2d(vor)
  center = vor.vertices;
  
  # detect inside points and connect to line
  ins = inside_polygon(polygon, center);
  center = np.vstack([leftcurve[0], center[ins], leftcurve[-1]]);
  center = sort_points_to_line(center);
  
  plt.figure(10); plt.clf();
  plt.plot(vor.vertices[:,0], vor.vertices[:,1], '.b');
  plt.plot(center[:,0], center[:,1], '.r');
  plt.plot(leftcurve[:,0], leftcurve[:,1]);
  plt.plot(rightcurve[:,0], rightcurve[:,1]);
  
  #from scipy.spatial import voronoi_plot_2d
  #voronoi_plot_2d(vor)
  
  center = resample_curve(center, npoints, smooth = smooth);
  
  if not with_width:
    return center;
  
  # calculate normals along midline and intersection to left/right curves
  width = np.zeros(npoints);
  
  rightline = geom.LineString(rightcurve);
  leftline  = geom.LineString(leftcurve);
  
  for i in range(npoints):
    mid_point = geom.Point(center[i,0], center[i,1]);
    right_point = rightline.interpolate(rightline.project(mid_point));
    left_point  =  leftline.interpolate( leftline.project(mid_point));
    width[i] = np.linalg.norm(np.array([left_point.x - right_point.x, left_point.y - right_point.y]));

  return center, width
  

def center_from_sides_projection(left, right, npoints = all, nsamples = all, resample = False, with_width = False, nneighbours = all, smooth = 0):
  """Finds middle line between the two side curves using projection method
  
  Arguments:
    left, right (nx2 array): vertices of the left and right curves
    npoints (int or all): number of points of the mid line
    nsamples (int or all): number of sample points to contruct midline
    with_width (bool): if True also return estimated width
    nneighbours (int or all): number of neighbouring points to include for projection
  
  Returns:
    nx2 array of midline vertices
  """
  # resample to same size
  nl = left.shape[0];
  nr = right.shape[0];
  if nsamples is all:
    nsamples = max(nl,nr);
  if npoints is all:
    npoints = max(nl,nr);
  
  if nl != nsamples or nr != nsamples or resample:
    leftcurve  = resample_curve(left, nsamples);
    rightcurve = resample_curve(right, nsamples);
  else:
    leftcurve = left;
    rightcurve = right;
  
  # calculate center
  center = np.zeros((nsamples,2));
    
  if nneighbours is all:
    rightline = geom.LineString(rightcurve);
    leftline  = geom.LineString(leftcurve);
  
    for i in range(nsamples):
      right_point = geom.Point(rightcurve[i,0], rightcurve[i,1]);
      left_point  = geom.Point(leftcurve[i,0], leftcurve[i,1]);
        
      right_left_point =  leftline.interpolate( leftline.project(right_point));
      left_right_point = rightline.interpolate(rightline.project( left_point));
      
      center[i] = 0.25 * np.array([right_point.x + left_point.x + right_left_point.x + left_right_point.x,
                                   right_point.y + left_point.y + right_left_point.y + left_right_point.y]);
      
    center = resample_curve(center, npoints, smooth = smooth);
  
    if not with_width:
      return center;
    
    # calculate normals along midline and intersection to left/right curves
    width = np.zeros(npoints);
    
    rightline = geom.LineString(rightcurve);
    leftline  = geom.LineString(leftcurve);
    
    for i in range(npoints):
      mid_point = geom.Point(center[i,0], center[i,1]);
      right_point = rightline.interpolate(rightline.project(mid_point));
      left_point  =  leftline.interpolate( leftline.project(mid_point));
      width[i] = np.linalg.norm(np.array([left_point.x - right_point.x, left_point.y - right_point.y]));
  
    return center, width

  else: # only consider a certain subset of neighbours in projection (useful when worm is highly bend)
    #nneighbours2 = int(np.ceil(nneighbours/2.0));
    nneighbours2 = nneighbours;
    for i in range(nsamples):
      il = max(0, i-nneighbours2);
      ir = min(i+nneighbours2, nsamples);
      
      rightline = geom.LineString(rightcurve[il:ir]);
      leftline  = geom.LineString( leftcurve[il:ir]);
      
      right_point = geom.Point(rightcurve[i,0], rightcurve[i,1]);
      left_point  = geom.Point(leftcurve[i,0], leftcurve[i,1]);
        
      right_left_point =  leftline.interpolate( leftline.project(right_point));
      left_right_point = rightline.interpolate(rightline.project( left_point));
      
      center[i] = 0.25 * np.array([right_point.x + left_point.x + right_left_point.x + left_right_point.x,
                                   right_point.y + left_point.y + right_left_point.y + left_right_point.y]);
    
    center = resample_curve(center, npoints, smooth = smooth);

    if not with_width:
      return center;
    
    # calculate normals along midline and intersection to left/right curves
    width = np.zeros(npoints);
    
    for i in range(nsamples):
      il = max(0, i-nneighbours2);
      ir = min(i+nneighbours2, nsamples);
      
      rightline = geom.LineString(rightcurve[il:ir]);
      leftline  = geom.LineString( leftcurve[il:ir]);
      
      mid_point = geom.Point(center[i,0], center[i,1]);
      right_point = rightline.interpolate(rightline.project(mid_point));
      left_point  =  leftline.interpolate( leftline.project(mid_point));
      width[i] = np.linalg.norm(np.array([left_point.x - right_point.x, left_point.y - right_point.y]));
    
    return center, width



def center_from_sides_min_projection(left, right, npoints = all, nsamples = all, resample = False, with_width = False, smooth = 0, center_offset = 2):
  """Finds middle line between the two side curves using projection method with minimal  advancements
  
  Arguments:
    left, right (nx2 array): vertices of the left and right curves
    npoints (int or all): number of points of the mid line
    nsamples (int or all): number of sample points to contruct midline
    with_width (bool): if True also return estimated width
    nneighbours (int or all): number of neighbouring points to include for projection
  
  Returns:
    nx2 array of midline vertices
  """
  # resample to same size
  nl = left.shape[0];
  nr = right.shape[0];
  if nsamples is all:
    nsamples = max(nl,nr);
  if npoints is all:
    npoints = max(nl,nr);
  
  if nl != nsamples or nr != nsamples or resample:
    leftcurve  = resample_curve(left, nsamples);
    rightcurve = resample_curve(right, nsamples);
  else:
    leftcurve = left;
    rightcurve = right;
  
  # calculate center
  full_left = [leftcurve[i] for i in range(center_offset)];
  full_right = [rightcurve[i] for i in range(center_offset)];
  width = [0];
  il = center_offset-1; ir = center_offset-1;
  rightline = geom.LineString(rightcurve[il:il+2]);
  leftline  = geom.LineString( leftcurve[ir:ir+2]); 
  
  il = center_offset; ir = center_offset;
  left_point  = geom.Point(leftcurve[il,0], leftcurve[il,1]);
  right_point = geom.Point(rightcurve[ir,0], rightcurve[ir,1]); 
  
  while il < nsamples-center_offset-1 and ir < nsamples-center_offset-1:
    #print il,ir
    ul = leftline.project(right_point, normalized = True);
    ur = rightline.project(left_point, normalized = True);
    #print ul,ur
    #print left_point, right_point
    if ul == ur:
      full_left.append(left_point.coords[0]);
      full_right.append(right_point.coords[0]);
      leftline = geom.LineString(leftcurve[il:il+2]);
      rightline = geom.LineString(rightcurve[ir:ir+2]);
      il+=1;
      ir+=1;
      left_point = geom.Point(leftcurve[il,0], leftcurve[il,1]);
      right_point = geom.Point(rightcurve[ir,0], rightcurve[ir,1]);
    elif ul < ur: # add center from right
      full_left.append(leftline.interpolate(ul, normalized = True).coords[0]);
      full_right.append(right_point.coords[0]);
      rightline = geom.LineString(rightcurve[ir:ir+2]);
      ir+=1;
      right_point = geom.Point(rightcurve[ir,0], rightcurve[ir,1]);
    else:
      full_left.append(left_point.coords[0]);
      full_right.append(rightline.interpolate(ur, normalized = True).coords[0]);
      leftline = geom.LineString(leftcurve[il:il+2]);
      il+=1;
      left_point = geom.Point(leftcurve[il,0], leftcurve[il,1]);
  
  
  full_left.extend([leftcurve[i] for i in range(-center_offset,0)]);
  full_right.extend([rightcurve[i] for i in range(-center_offset,0)]);
  
  full_left = np.array(full_left);
  full_right = np.array(full_right);
  
  #print full_left
  #print full_right
  center = (full_left + full_right)/2.0;
  center = resample_curve(center, npoints, smooth = smooth);
  
  #print center
  
  if not with_width:
    return center;
  else:
    width = np.linalg.norm(full_left-full_right, axis = 1);
    width = 0.5 * resample_curve(width, npoints, smooth = 0);
    #lc = np.asarray(leftcurve, dtype = 'float32');
    #rc = np.asarray(rightcurve, dtype = 'float32');
    #cnt = np.vstack(lc, rc[::-1]);
    #width_l = np.array([np.min(np.linalg.norm(leftcurve - c, axis = 1)) for c in center])  
    #width_r = np.array([np.min(np.linalg.norm(rightcurve - c, axis = 1)) for c in center])  
    
    #width_l = np.array([cv2.pointPolygonTest(lc,(c[0],c[1]),True) for c in center]);
    #width_r = np.array([cv2.pointPolygonTest(rc,(c[0],c[1]),True) for c in center]);
    #width = (width_l + width_r); 
    #width = 2* np.min([width_l, width_r], axis = 0);
    #width[[0,-1]] = 0.0;
  
    return center, width



def center_from_sides_mean(left, right, npoints = all, nsamples = all, resample = False, with_width = False):
  """Finds middle line between the two side curves by simply taking the mean
  
  Arguments:
    left, right (nx2 array): vertices of the left and right curves
    npoints (int or all): number of points of the mid line
    nsamples (int or all): number of sample points to contruct midline
    with_width (bool): if True also return estimated width
  
  Returns:
    nx2 array of midline vertices
  """

  # resample to same size
  nl = left.shape[0];
  nr = right.shape[0];
  if nsamples is all:
    nsamples = max(nl,nr);
  if npoints is all:
    npoints = max(nl,nr);
  
  if nl != nsamples or nr != nsamples or resample:
    leftcurve  = resample_curve(left, nsamples);
    rightcurve = resample_curve(right, nsamples);
  else:
    leftcurve = left;
    rightcurve = right;

  center = (leftcurve + rightcurve) / 2;
  
  if npoints != nsamples:
    center = resample_curve(center, npoints);
  
  if with_width:
    width  = np.linalg.norm(leftcurve - rightcurve, axis = 0);
    return center, width
  else:
    return center;
    

def center_from_sides_erosion(left, right, erode = 0.1, maxiter = 100, delta = 0.3, ncontour = 100, smooth = 1.0, npoints = all, nsamples = all, resample = False, with_width = False, verbose = False):
  """Finds middle line between the two side curves by simply taking the mean
  
  Arguments:
    left, right (nx2 array): vertices of the left and right curves
    npoints (int or all): number of points of the mid line
    nsamples (int or all): number of sample points to contruct midline
    with_width (bool): if True also return estimated width
  
  Returns:
    nx2 array of center line vertices
  """

  # resample to same size
  nl = left.shape[0];
  nr = right.shape[0];
  if nsamples is all:
    nsamples = max(nl,nr);
  if npoints is all:
    npoints = max(nl,nr);
  
  if nl != nsamples or nr != nsamples or resample:
    leftcurve  = resample_curve(left, nsamples);
    rightcurve = resample_curve(right, nsamples);
  else:
    leftcurve = left;
    rightcurve = right;

  #construct polygon and erode
  poly = geom.polygon.Polygon(np.vstack([leftcurve, rightcurve[::-1,:]]));
  
  last = poly;
  w = 0;
  for i in range(maxiter):
    new = last.buffer(-erode);
    if not isinstance(new.boundary, geom.linestring.LineString):
      new = last;
      break;
    last = new;
    w += erode;
    #x,y = new.boundary.xy
    #plt.plot(x, y, color='r', alpha=0.7, linewidth=3, solid_capstyle='round', zorder=2)
  
  x,y = last.boundary.xy;
  pts = np.vstack([x[:-1],y[:-1]]).T;
  
  if ncontour is all:
    ncontour = pts.shape[0];

  #plt.plot(pts[:,0], pts[:,1], 'm')
  #print pts
  
  #detect high curvatuerpoints along the contour 
  cinterp, u = splprep(pts.T, u = None, s = smooth, per = 1) 
  us = np.linspace(u.min(), u.max(), ncontour)
  x, y = splev(us[:-1], cinterp, der = 0)

  ### curvature along the points
  dx, dy = splev(us[:-1], cinterp, der = 1)
  d2x, d2y = splev(us[:-1], cinterp, der = 2)
  k = (dx * d2y - dy * d2x)/np.power(dx**2 + dy**2, 1.5);
  
  ### find tail / head via peak detection
  #pad k to detect peaks on both sides
  nextra = 20;
  kk = -k; # negative curvature peaks are heads/tails
  kk = np.hstack([kk,kk[:nextra]]);
  peaks = find_peaks(kk, delta = delta);

  if peaks.shape[0] > 0:  
    peaks = peaks[peaks[:,0] < k.shape[0],:];
  else:
    peaks = np.zeros((0,2));
  
  #print peaks
  if peaks.shape[0] < 2:
    if peaks.shape[0] == 1:
      # best guess is half way along the contour
      if verbose:
        print('Could only detect single curvature peak in contour, proceeding with opposite point as tail!')
      imax = np.sort(np.asarray(np.mod(peaks[0,0] + np.array([0,ncontour//2]), ncontour), dtype = int));
    else:
      if verbose:
        print('Could not detect any peaks in contour, proceeding with 0% and 50% of contour as head and tail!')
      imax = np.asarray(np.round([0, ncontour//2]), dtype = int);
  else:
    imax = np.sort(np.asarray(peaks[np.argsort(peaks[:,1])[-2:],0], dtype = int))
  #print imax  
  
  ### calcualte sides and midline
  u1 = np.linspace(us[imax[0]], us[imax[1]], npoints-2)
  x1, y1 =  splev(u1, cinterp, der = 0);
  left = np.vstack([x1,y1]).T;
  
  u2 = np.linspace(us[imax[0]], us[imax[1]]-1, npoints-2);
  u2 = np.mod(u2,1);
  x2, y2 = splev(u2, cinterp, der = 0);
  right = np.vstack([x2,y2]).T;
  
  center = (left + right) / 2;
  center = np.vstack([leftcurve[0], center, leftcurve[-1]]);
  
  #plt.plot(center[:,0], center[:,1], 'k')
  
  if with_width:
    width = np.vstack([0, np.linalg.norm(left - right, axis = 0) + w, 0]);
    cw = np.hstack([center, width[:,np.newaxis]]);
    cw = resample_curve(cw, npoints);
    center = cw[:,:2]; width = cw[:,-1];
    return center, width
  else:
    return resample_curve(center, npoints);
    
    



def center_from_sides(left, right, npoints = all, nsamples = all, resample = False, with_width = False, smooth = 0,  nneighbours = all, method = 'projection'):
  """Finds middle line between the two side curves
  
  Arguments:
    left, right (nx2 array): vertices of the left and right curves
    npoints (int or all): number of points of the mid line
    nsamples (int or all): number of sample points to contruct midline
    with_width (bool): if True also return estimated width
    nneighbours (int or all): number of neighbouring points to include for projection
    method ({'projection', 'vonroi', 'mean'}): the method to calculate midline
  
  Returns:
    nx2 array of midline vertices
  """
  
  if method == 'projection':
    return center_from_sides_projection(left, right, npoints = npoints, nsamples = nsamples, resample = resample, with_width = with_width, nneighbours = nneighbours, smooth = smooth);
  elif method == 'vonroi':
    return center_from_sides_vonroi(left, right, npoints = npoints, nsamples = nsamples, resample = resample, with_width = with_width, smooth = smooth);
  else:
    return center_from_sides_mean(left, right, npoints = npoints, nsamples = nsamples, resample = resample, with_width = with_width);



def length_from_center_discrete(center):
  """Returns the length of the center line
  
  Arguments:
    center (nx2 array): center line points
  
  Returns
    float: length of center line
  """
  ds = np.diff(center, axis = 0);
  return np.sum(np.sqrt(np.sum(ds*ds, axis = 1)));
  

def center_of_center_discrete(center):
  """Returns the center along the worm's center line"""
  n = len(center);
  n2 = n//2;
  if n % 2 == 0:
    return (center[n2-1] + center[n2])/2;
  else:
    return center[n2];


def rotate_center_discrete(center, rad, pos = [75,75]):
  """Rotate the center line"""
  if pos is None:
    pos = center_of_center_discrete(center);
  r = np.array([[np.cos(rad), -np.sin(rad)],[np.sin(rad), np.cos(rad)]]);
  return np.dot(center - pos, r.T) + pos


##########################################################################
### Center Line Bending

def lift_cirular(phi):
  """Lifts circular/angular valued curve to avoid discontinuities, assumes phi in range [-pi,pi]"""
  dphi = np.diff(phi);
  ii = np.where(dphi < -np.pi)[0]+1;
  ip = np.where(dphi > np.pi)[0]+1;

  lift = np.zeros(phi.shape);
  for i in ii:
    lift[i:] += 2 * np.pi;
  for i in ip:
    lift[i:] -= 2 * np.pi;
  
  return phi + lift;
  
  
def theta_from_center_discrete(center, npoints = all, nsamples = all, resample = False, smooth = 0):
  """Calculates bending angle theta along the center line using discrete mesh
  
  Arguments:
    center (nx2 array): center line
    npoints (int or all): number of final sample points for the center line
    nsamples (int) or all): number of sample points to construct theta
    resample (bool): forces uniform resampling if True
    smooth (float): smoothing factor for final sampling
  
  Returns:
    array: uniformly sampled bending angle along the center line
    float: absolute orientation with respect to vertical reference [1,0] at center of the worm
  
  Note:
    There are npoints - 2 angles along the center line, so the returned array 
    will be of length npoints-2.
    The returned points are samples of the deivative of the angle of the tangent 
    :math:`\\theta`: along the curve.
    The theta values are thus obtained via :math:`\that(s) \\approx = \\Delta \theta / \\Delta s`  
    and thus will be rescaled by the inverse 1/(npoints-2).
    The rescaling ensures that the spline represenation and integration return
    theta and phi.
  """
  
  nc = center.shape[0];
  
  if npoints is all:
    npoints = nc;
  if nsamples is all:
    nsamples = nc;
  n2 = (nsamples-1)//2;
  #n2a= (nsamples-2)//2;
  
  # resample center lines 
  if nsamples != nc or resample:
    centercurve = resample_curve(center, nsamples);
  else:
    centercurve = center;

  #vectors along center line
  centervec = np.diff(centercurve, axis = 0);
  
  # orientation
  t0 = np.array([1,0], dtype = float); #vertical reference
  #t1 = (centervec[n2] + centervec[n2a])/2.0;
  t1 = centervec[n2];
  orientation = np.mod(np.arctan2(t0[0], t0[1]) - np.arctan2(t1[0], t1[1]) + np.pi, 2 * np.pi) - np.pi;
  
  # xy
  #xy = (centercurve[n2]+centercurve[n2a])/2.0;
  xy = centercurve[n2];
  
  # thetas
  theta = np.arctan2(centervec[:-1,0], centervec[:-1,1]) - np.arctan2(centervec[1:,0], centervec[1:,1]);
  theta = np.mod(theta + np.pi, 2 * np.pi) - np.pi;
  theta *= (nsamples-1); # when spline is used later on this is the right scaling in the continous limit
  
  #length
  length = np.linalg.norm(centervec, axis = 1).sum();

  if npoints != nsamples or resample:
    theta = resample_curve(theta, npoints - 2, smooth = smooth);
  
  return theta, orientation, xy, length



def theta_from_center_spline(center, npoints = all, nsamples = all, resample = False, smooth = 0):
  """Calculates bending angle theta along the center line using splines
  
  Arguments:
    center (nx2 array): center line
    npoints (int or all): number of final sample points for the center line
    nsamples (int) or all): number of sample points to construct theta
    resample (bool): forces uniform resampling if True
    smooth (float): smoothing factor for final sampling
  
  Returns:
    array: uniformly sampled bending angle along the center line
    float: absolute orientation with respect to vertical reference [1,0] at center of the worm
  
  Note:
    There are npoints - 2 angles along the center line, so the returned array will be of length npoints-2
  """
  
  nc = center.shape[0];
  
  if npoints is all:
    npoints = nc;
  if nsamples is all:
    nsamples = nc;
  
  #if nsamples % 2 != 1:
  #  raise RuntimeWarning('number of sample points expected to be odd adding a sample point!')
  #  nsamples += 1;
  n2 = (nsamples-1)//2;
  
  # resample center lines 
  if nsamples != nc or resample:
    centercurve = resample_curve(center, nsamples);
  else:
    centercurve = center;

  #vectors along center line
  centervec = np.diff(centercurve, axis = 0);
    
  # xy
  xy = centercurve[n2];
  
  #length
  length = np.linalg.norm(centervec, axis = 1).sum();
  
  # thetas
  phi = np.arctan2(centervec[:-1,0], centervec[:-1,1]);
  phi = lift_cirular(phi);
  phisp = Spline(phi);
  
  theta = phisp.derivative();
  
  orientation = phisp(0.5);
  
  points = np.linspace(0,1,npoints-2);
  theta = theta(points);
  
  return theta, orientation, xy, length


theta_from_center = theta_from_center_discrete;


def center_from_theta_discrete(theta, orientation = 0, xy = [0,0], length = 1, npoints = all, nsamples = all, resample = False, smooth = 0, with_normals = False):
  """Constructs center line from theta on discrete mesh
  
  Arguments:
    theta (nx2 array): angles along center line
    orientation (float): absolute orientation of the center line
    xy (2 array): absolute position of the center line
    length (float): length of center line
    npoints (int or all): number of final sample points along center line
    nsamples (int or all): number of sample points to construct center line
    resample (bool): for resampling if True
    smooth (float): smoothing factor for final sampling

  Returns
    npointsx2 array: the sample points along the center line
  
  Note:
    The theta sample length is 2 less than the curve sample length.
    The absolute angle is integral of theta so that for discrete integration 
    we multiply this curve with the discretized smaple length of 1/
  """

  nt = theta.shape[0];
  
  if npoints is all:
    npoints = nt + 2;
  if nsamples is all:
    nsamples = nt + 2;
  n2 = (nsamples-1)//2;
  #n2a= (nsamples-2)//2;
  
  # resample center lines 
  if nsamples != nt + 2 or resample:
    itheta = resample_curve(theta, nsamples - 2);
  else:
    itheta = theta;
  
  #cos/sin
  delta = 1.0 / (nsamples-1); # Delta s for discrete integration nsample points -> nsample-1 segments
  itheta = np.cumsum(np.hstack([0, itheta])) * delta;
  #itheta += orientation - (itheta[n2]+itheta[n2a])/2.0;
  itheta += orientation - itheta[n2];
  cos = np.cos(itheta);
  sin = np.sin(itheta);
  
  x = np.cumsum(cos);
  y = np.cumsum(sin);
  center = np.vstack([x,y]).T;
  center = np.vstack([[0,0], center]);
  center = float(length) * delta * center;
  #center += xy - (center[n2] + center[n2a+1])/2.0;
  center += xy - center[n2];
  
  if npoints != nsamples or resample:
    center = resample_curve(center, npoints, smooth = smooth);
  
  if with_normals:
    if npoints != nsamples:
      itheta = resample_curve(itheta, npoints - 1);
    dtheta = np.diff(itheta);
    itheta += np.pi/2;
    itheta = np.hstack([itheta, itheta[-1]]);
    itheta[1:-1] -= dtheta / 2;
    return center, np.vstack([np.cos(itheta), np.sin(itheta)]).T;
  else:
    return center;



def center_from_theta_spline(theta, orientation = 0, xy = [0,0], length = 1, npoints = all, nsamples = all, resample = False, smooth = 0, with_normals = False):
  """Constructs center line from theta via spline integration
  
  Arguments:
    theta (nx2 array or Spline): angles along center line
    orientation (float): absolute orientation of the center line
    xy (2 array): absolute position of the center line
    length (float): length of center line
    npoints (int or all): number of final sample points along center line
    nsamples (int or all): number of smaple points to construct center line
    resample (bool): for resampling if True
    smooth (float): smoothing factor for final sampling

  Returns
    npointsx2 array: the sample points along the center line
  """
  
  if isinstance(theta, np.ndarray):
    nt = theta.shape[0];  
    if npoints is all:
      npoints = nt + 2;
    theta = np.hstack([theta]);
    theta = Spline(theta);
  
  if nsamples is all:
    nsamples = npoints; 
  
  s = np.linspace(0,1,nsamples)
  istheta = theta.integral();
  ithetac = float(istheta(0.5));
  itheta = istheta(s); 
  #itheta = np.hstack([0, itheta]);
  itheta += orientation - ithetac;
  
  cos = np.cos(itheta);
  sin = np.sin(itheta);
  
  # integrate
  #s = np.linspace(0,1,nsamples-1);
  x = UnivariateSpline(s, cos).antiderivative();
  y = UnivariateSpline(s, sin).antiderivative();
  
  #s = np.linspace(0,1,nsamples);
  center = np.vstack([x(s),y(s)]).T;
  #center = np.vstack([[0,0], center]);
  center = length * center;
  center += xy - np.array([x(0.5), y(0.5)]);
  
  if npoints != nsamples or resample:
    center = resample_curve(center, npoints, smooth = smooth);
  
  if with_normals:
    if npoints != nsamples:
      itheta = istheta(np.linspace(0,1,npoints));
      itheta += orientation - ithetac;
    #dtheta = np.diff(itheta);
    #itheta += np.pi/2;
    #itheta[1:-1] -= dtheta / 2;
    return center, np.vstack([np.cos(itheta), np.sin(itheta)]).T;
  else:
    return center;

#center_from_theta = center_from_theta_discrete;
#theta_from_center = theta_from_center_discrete;

center_from_theta = center_from_theta_discrete;



def normals_from_theta_discrete(theta, orientation = 0, npoints = all, nsamples = all, resample = False):
  """Constructs normals from theta on discrete mesh
  
  Arguments:
    theta (nx2 array): angles along center line
    orientation (float): absolute orientation of the center line
    npoints (int or all): number of final sample points along center line
    nsamples (int or all): number of smaple points to construct center line
    resample (bool): for resampling if True

  Returns
    npointsx2 array: the normals along the sample points for the center line
  """

  nt = theta.shape[0];
  
  if npoints is all:
    npoints = nt + 2;
  if nsamples is all:
    nsamples = nt + 2;
  n2 = (nsamples-1)//2;
  #n2a= (nsamples-2)//2;
  
  # resample theta 
  if nsamples != nt + 2 or resample:
    itheta = resample_curve(theta, nsamples - 2);
  else:
    itheta = theta;
  
  #cos/sin
  delta = 1.0 / (nsamples-1); # Delta s for discrete integration nsample points -> nsample-1 segments
  itheta = np.cumsum(np.hstack([0, itheta])) * delta;
  #itheta += orientation - (itheta[n2]+itheta[n2a])/2.0;
  itheta += orientation - itheta[n2];
  
  if npoints != nsamples:
    itheta = resample_curve(itheta, npoints - 1);
  
  dtheta = np.diff(itheta);
  itheta += np.pi/2;
  itheta = np.hstack([itheta, itheta[-1]]);
  itheta[1:-1] -= dtheta / 2;
  
  return np.vstack([np.cos(itheta), np.sin(itheta)]).T;


normals_from_theta = normals_from_theta_discrete;


def normals_from_center_discrete(center):
  """Construct normals along center line
  
  Arguments:
    center (nx2 array): center line
  
  Returns:
    array (nx2): normals along center points
  """
  
  theta, orientation, xy, length = theta_from_center_discrete(center);
  return normals_from_theta_discrete(theta, orientation);
  

normals_from_center = normals_from_center_discrete;


def shape_from_theta_discrete(theta, width, orientation = 0, xy = [0,0], length = 1, npoints = all, nsamples = all, resample = False, smooth = 0, with_normals = False):
  """Construct center line from theta on discrete mesh
  
  Arguments:
    theta (nx2 array): angles along center line
    width (n array): width profile
    length (float): length of center line
    npoints (int or all): number of final sample points along center line
    nsamples (int or all): number of smaple points to construct center line
    resample (bool): for resampling if True
    smooth (float): smoothing factor for final sampling

  Returns
    array: the sample points along the left side
    array: the sample points along the right side
    array: the sample points along the center line
    array: the normal vector along the center points (if with_normals is True)
  
  Note:
    The theta sample length is 2 less than the curve sample length
    Returned normals
  """

  center, normals = center_from_theta_discrete(theta, orientation = orientation, xy = xy, length = length, 
                                               npoints = npoints, nsamples = nsamples, resample = resample, smooth = smooth, 
                                               with_normals = True)

  #w = np.hstack([0, width, 0]);  # assume zero width at head an tail
  if width.shape[0] != center.shape[0]:
    w = resample_curve(width, npoints = center.shape[0]);
  else:
    w = width;
  w = np.vstack([w,w]).T;
  left  = center + 0.5 * w * normals;
  right = center - 0.5 * w * normals;

  if with_normals:
    return left, right, center, normals
  else:
    return left, right, center
  


def shape_from_theta_spline(theta, width, orientation = 0, xy = [0,0], length = 1, npoints = all, nsamples = all, resample = False, smooth = 0, with_normals = False):
  """Constructs center line from theta on discrete mesh
  
  Arguments:
    theta (nx2 array): angles along center line
    width (n array): width profile
    length (float): length of center line
    npoints (int or all): number of final smaple points along center line
    nsamples (int or all): number of smaple points to construct center line
    resample (bool): for resampling if True
    smooth (float): smoothing factor for final sampling

  Returns
    array: the sample points along the center line
    array: the sample points along the left side
    array: the sample points along the right side
    array: the normal vector along the center points (if with_normals is True)
  
  Note:
    The theta sample length is 2 less than the curve sample length
    Returned normals
  """

  center, normals = center_from_theta_spline(theta, orientation = orientation, xy = xy, length = length, 
                                             npoints = npoints, nsamples = nsamples, resample = resample, smooth = smooth, 
                                             with_normals = True)

  #w = np.hstack([0, width, 0]);  # assume zero width at head an tail
  if width.shape[0] != center.shape[0]:
    w = resample_curve(width, npoints = center.shape[0]);
  else:
    w = width;
  w = np.vstack([w,w]).T;
  left  = center + 0.5 * w * normals;
  right = center - 0.5 * w * normals;

  if with_normals:
    return center, left, right, normals
  else:
    return center, left, right


shape_from_theta = shape_from_theta_discrete;


def shape_from_center_discrete(center, width, normals = None, with_normals = False):
  """Get side lines from center and width
  
  Arguments:
    center (nx2 array): center line
    width (n array): width profile
    normals (nx2 or None): normals, if None calculate
    with_normals (bool): if True also return normals
  
  Returns:
    tuple of arrays (nx2): left, right lines and normals
    
  """
  
  if width.shape[0] != center.shape[0]:
    w = resample_curve(width, npoints = center.shape[0]);
  else:
    w = width;
  w = np.vstack([w,w]).T;
  
  if normals is None:
    normals = normals_from_center_discrete(center);
  
  left  = center + 0.5 * w * normals;
  right = center - 0.5 * w * normals;

  if with_normals:
    return left,right,normals
  else:
    return left, right


shape_from_center = shape_from_center_discrete;


def test_theta():
  from importlib import reload
  import numpy as np
  import matplotlib.pyplot as plt;
  import worm.geometry as sh;
  reload(sh);
  
  #test lift
  phi = np.array([0,1,2,3,-3, -2, -1, -2, -3, 3, 2]);
  phil = sh.lift_cirular(phi);
  plt.figure(100); plt.clf();
  plt.plot(phi);
  plt.plot(phil);

  #test center from theta
  reload(sh);
  nn = 152;
  th = np.ones(nn) * np.pi;
  th2 = np.sin(np.linspace(0, 2, nn)) * np.pi;  
  c = sh.center_from_theta_discrete(th);
  c2 = sh.center_from_theta_discrete(th, orientation =-np.pi/2, xy = [1,1]);
  c3 = sh.center_from_theta_discrete(th2, orientation = -np.pi, xy = [-1,-1]);
  
  plt.figure(1); plt.clf();
  plt.plot(c[:,0], c[:,1]);
  plt.plot(c2[:,0], c2[:,1]);
  plt.plot(c3[:,0], c3[:,1]);
  
  # center form theta spline
  reload(sh);
  sc = sh.center_from_theta_spline(th);
  sc2 = sh.center_from_theta_spline(th, orientation = -np.pi/2, xy = [1,1]);
  sc3 = sh.center_from_theta_spline(th2, orientation = -np.pi, xy = [-1,-1]);
  
  #plt.figure(2); plt.clf();
  plt.plot( sc[:,0],  sc[:,1]);
  plt.plot(sc2[:,0], sc2[:,1]);
  plt.plot(sc3[:,0], sc3[:,1]);
  plt.axis('equal')
  plt.tight_layout();
  
  from utils.timer import timeit
  @timeit
  def ts():
    return sh.center_from_theta_spline(th, orientation = -np.pi, xy = [-1,-1]);
  @timeit
  def td():
    return sh.center_from_theta_discrete(th, orientation = -np.pi, xy = [-1,-1]);
  cs = ts();
  cd = td();
  np.allclose(cs, cd);
  

  #test inversions
  reload(sh);
  nn = 11;
  th = np.ones(nn) * np.pi;
  th = np.sin(np.linspace(0, 2, nn)) * np.pi;  
  c = sh.center_from_theta_discrete(th, orientation = -np.pi, xy = [-1,-1]); 
  thi, oi, xyi, li  = sh.theta_from_center_discrete(c)
  ci = sh.center_from_theta_discrete(thi, oi, xyi, li);
  np.allclose(th, thi);
  np.allclose(-np.pi, oi);
  np.allclose([-1,-1], xyi);
  np.allclose(1, li)
  np.allclose(c,ci)
  
  plt.figure(1); plt.clf();
  plt.plot(c[:,0], c[:,1]);
  plt.plot(ci[:,0], ci[:,1]);

  # test normals
  reload(sh);
  th = np.sin(np.linspace(0, 2, 8)) * 3;  
  c,n = sh.center_from_theta(th, orientation = -np.pi, xy = [-1,-1], length = 10, with_normals=True);
  plt.figure(2); plt.clf();
  plt.plot(c[:,0], c[:,1]);
  cp = c + n;
  cm = c - n;
  for i in range(n.shape[0]):
    plt.plot([cp[i,0], cm[i,0]], [cp[i,1], cm[i,1]], 'r');
  plt.axis('equal')
  
  # test shape from theta
  reload(sh);
  th = np.sin(np.linspace(0, 2, 8)) * 0.3;  
  width = 1-np.cos(np.linspace(0, 2*np.pi, 10));
  center, left, right = sh.shape_from_theta(th, width, orientation = -np.pi, xy = [-1,-1], length = 10, with_normals=False)
  
  plt.figure(13); plt.clf();
  plt.plot(left[:,0]  ,left[:,1]  , 'g', linewidth= 3)
  plt.plot(right[:,0] ,right[:,1] , 'y', linewidth= 3)
  plt.plot(center[:,0],center[:,1], 'b')
  plt.axis('equal')
  
  #how does center line recovery work
  c2 = sh.center_from_sides(left, right, nneighbours = 30, nsamples = 100);  
  c3 = sh.center_from_sides_mean(left, right);
  plt.plot(c3[:,0], c3[:,1]);
  plt.plot(c2[:,0], c2[:,1], 'r');





##############################################################################
### Worm Motions

def move_forward_center_discrete(distance, center, straight = True):
  """Move worm forward peristaltically
  
  Arguments:
    distance (float): distance to move forward
    center (nx2 array): center points
    length (float or None): length to use for position update
    straight (bool): if True extrapolated points move straight
    
  Note:
    The head is first point in center line and postive distances will move the
    worm in this direction.
  """  
  cinterp, u = splprep(center.T, u = None, s = 0, per = 0)
  us = u - distance;
  x, y = splev(us, cinterp, der = 0); 
  cline2 = np.array([x,y]).T;   
  
  if straight:
     l = length_from_center_discrete(center);
     if distance > 0:
       idx = np.where(us < 0)[0];
       if len(idx) > 0:
         d = center[0,:] - center[1,:];
         d = d / np.linalg.norm(d) * l;
         for i in idx:
           cline2[i,:] = center[0,:] - d * us[i];
     elif distance < 0:
       idx = np.where(us > 1)[0];
       if len(idx) > 0:
         d = center[-1,:] - center[-2,:];
         d = d / np.linalg.norm(d) * l;
         for i in idx:
           cline2[i,:] = center[-1,:] + d * (us[i]-1);
    
  return cline2;

  
def move_forward_discrete(distance, theta, orientation, xy, length, straight = True):
  """Move worm forward peristaltically
  
  Arguments:
    distance (float): distance to move forward
    theta (nx2 array): discrete bending angles
    orientation (float or None): orientation to update
    xy (array or None): position to update
    length (float or None): length to use for position update
    straight (bool): if True extrapolated points move straight
    
  Note:
    The head is first point in center line and postive distances will move the
    worm in this direction.
  """  
  cline = center_from_theta_discrete(theta, orientation = orientation, xy = xy, length = length, npoints = all, nsamples = all, resample = False, with_normals = False);
  cline2 = move_forward_center_discrete(distance, cline, straight);
  return theta_from_center_discrete(cline2, npoints = all, nsamples = all, resample = False);
  
  

def move_forward_spline(distance, theta, orientation = None, xy = None, length = None):
  """Moves the worh forward presitaltically
  
  Arguments:
    distance (float): distance to move forward
    theta (Spline): spline of the center bending angle
    orientation (float or None): orientation to update
    xy (array or None): position to update
    length (float or None): length to use for position update
  
  Returns:
    Spline: shifted theta
    array: shifted position
    float: shifted orientation
  
  Note:
    Positive distacnes will move worm in direction to first point (head).
  """
     
  #shift theta
  theta.shift(distance);

  res = [theta];   
  if xy is not None or orientation is not None:

    dd = max(min(distance, 0.5), -0.5);
    dp = distance - dd;    
  
    #integrated angles
    phii = theta.integral();
    if orientation is None:
      o = 0.0; 
    else:
      o = orientation;
    phii.add(-phii(0.5) + o);
  
    #orientation
    if orientation is not None:
      res.append( orientation + phii(0.5 + dd) - phii(0.5));
  
    #xy shift
    if xy is not None:
      if length is None:
        length = 1.0;
      
      dx =  length * phii.integrate(0.5, 0.5 + distance, function = np.cos);
      dy =  length * phii.integrate(0.5, 0.5 + distance, function = np.sin);
      if dp > 0:
        dx += np.cos(phii(1.0)) * dp * length;
        dy += np.sin(phii(1.0)) * dp * length;
      elif dp < 0:
        dx += np.cos(phii(0.0)) * dp * length;
        dy += np.sin(phii(0.0)) * dp * length;
      res.append(xy + [dx,dy]);
    
    return tuple(res);




##############################################################################
### Shape Detection from Image 


def shape_from_image(image, sigma = 1, absolute_threshold = None, threshold_factor = 0.95, 
                     ncontour = 100, delta = 0.3, smooth_head_tail = 1.0, smooth_left_right = 1.0, smooth_center = 10,
                     npoints = 21, center_offset = 3, 
                     threshold_reduce = 0.9, contour_hint = None, size_hint = None,
                     delta_reduce = 0.5, head_tail_hint = None,
                     verbose = False, save = None):
  """Detect non self intersecting shapes of the the worm
  
  Arguments:
    image (array): the image to detect worm from
    sigma (float or None): width of Gaussian smoothing on image, if None use raw image
    absolute_threshold (float or None): if set use this as the threshold, if None the threshold is set via Otsu
    threshold_level (float): in case the threshold is determined by Otsu multiply by this factor
    ncontour (int): number of vertices in the contour
    delta (float): min height of peak in curvature to detect the head
    smooth (float): smoothing to use for the countour 
    nneighbours (int): number of neighbours to consider for midline detection
    npoints (int): number of vertices in the final center and side lines of the worm
    nsamples (int): number of vertices for center line detection
    verbose (bool): plot results
    save (str or None): save result plot to this file
  
  Returns:
    status (bool): 0 the shape was successfully extracted, otherwise id of what method was used or which failure
    arrays (npointsx2): center, left, right side lines of the worm
    
  Note:
    This is a fast way to detect the worm shape, fails for worms intersecting themselves
  """
  
  ### smooth image
  if sigma is not None:
    imgs = filters.gaussian_filter(np.asarray(image, float), sigma);
  else:
    imgs = image;
   
  ### get contours
  if absolute_threshold is not None:
    level = absolute_threshold;
  else:
    level = threshold_factor * threshold_otsu(imgs);
  
  pts, hrchy = detect_contour(imgs, level, with_hierarchy = True);
  if verbose:
    print("Found %d countours!" % len(pts));
    if verbose:
      plt.subplot(2,3,3)
      plt.imshow(imgs, cmap = 'gray')
      for p in pts:
        plt.plot(p[:,0], p[:,1]);
      plt.contour(imgs, levels = [level])
      plt.title('contour dectection')       
  
  status = 0;   
  if len(pts) == 0:
    if threshold_reduce is not None:
      pts, hrchy = detect_contour(imgs, threshold_reduce * level, with_hierarchy = True);
      status += 1000;
    
    if len(pts) == 0: # we cannot find the worm and give up...
      
      return -1, np.zeros((npoints,2)), np.zeros((npoints,2)), np.zeros((npoints,2), np.zeros(npoints))

  
  if len(pts) == 1:
    pts = pts[0];
    status += 1;
  
  else:   # length is  >= 2
    # remove all contours that are children of others

    outer = np.where(hrchy[:,-1] == -1 )[0];
    areas = np.array([cv2.contourArea(pts[o]) for o in outer]);
    outer = outer[areas > 0];

    print(outer)
    
    if len(outer) == 1:
      pts = pts[outer[0]]; # only one outer contour (worm mostlikely curled)
      status += 2;
      
    else:
      # is there contour with similar centroid and size to previous one
      moments = [cv2.moments(pts[o]) for o in outer];
      centroids = np.array([[(m["m10"] / m["m00"]), (m["m01"] / m["m00"])] for m in moments]);
      
      if contour_hint is not None:
        dist = [cv2.matchShapes(pts[o], contour_hint, 2,0) for o in outer];
        imin = np.argmin(dist);
        status += 3;
        pts = pts[outer[imin]]; 
      elif size_hint is not None:
        dist = np.array([cv2.contourArea(pts[o]) for o in outer]);
        dist = np.abs(dist - size_hint);
        imin = np.argmin(dist);
        status += 4;
        pts = pts[outer[imin]]; 
      else:
        #take most central one
        dist = np.linalg.norm(centroids - np.array(image.shape)/2, axis = 1);
        print(dist)
        imin = np.argmin(dist);
        status += 5;
        pts = pts[outer[imin]];
        
      print(status, len(pts))

  print('interpolate')
   
  
  ### interpolate outer contour
  nextra = min(len(pts)-1, 20); # pts[0]==pts[-1] !!
  print(pts[0], pts[-1])
  ptsa = np.vstack([pts[-nextra:], pts, pts[:nextra]]);
  cinterp, u = splprep(ptsa.T, u = None, s = smooth_head_tail, per = 0, k = 4) 
  u0 = u[nextra];
  u1 = u[-nextra-1];
  us = np.linspace(u0, u1, ncontour+1)[:-1];
  x, y = splev(us, cinterp, der = 0)
  dx, dy = splev(us, cinterp, der = 1)
  d2x, d2y = splev(us, cinterp, der = 2)
  k = - (dx * d2y - dy * d2x)/np.power(dx**2 + dy**2, 1.5);
  kk = np.hstack([k[-nextra:], k, k[:nextra]]);
  
  peak_ids, peak_values = find_peaks(kk, delta = delta);
  
  if len(peak_ids) > 0:
    peak_ids -= nextra;
    peak_values = peak_values[peak_ids>= 0]; peak_ids = peak_ids[peak_ids>= 0];  
    peak_values = peak_values[peak_ids < ncontour]; peak_ids = peak_ids[peak_ids < ncontour]; 
  
  if len(peak_ids) < 2 and delta_reduce is not None:
    peak_ids, peak_values = find_peaks(kk, delta = delta * delta_reduce);

    if len(peak_ids) > 0:
      peak_ids -= nextra;
      peak_values = peak_values[peak_ids>= 0]; peak_ids = peak_ids[peak_ids>= 0];  
      peak_values = peak_values[peak_ids < ncontour]; peak_ids = peak_ids[peak_ids < ncontour]; 

  if verbose:
    print('Found %d peaks' % len(peak_ids));

  # find head and tail
  if len(peak_ids) >= 2:
    if head_tail_hint is not None:
      xy = np.array([x[peak_ids], y[peak_ids]]).T;
      dist_h = np.linalg.norm(xy - head_tail_hint[0], axis = 1);
      dist_t = np.linalg.norm(xy - head_tail_hint[1], axis = 1);
      
      i_h = np.argmin(dist_h);
      i_t = np.argmin(dist_t);      
      if i_h == i_t:
        dist_t[i_t] = np.inf;
        i_t = np.argmin(dist_t);        
      
      imax = [peak_ids[i_h], peak_ids[i_t]];   
      status += 10;
      
    else:
      # best guess are the two highest ones
      imax = np.sort(np.asarray(peak_ids[np.argsort(peak_values)[-2:]], dtype = int))
      status += 20;
  
  elif len(peak_ids) == 1:
    if head_tail_hint is not None:
      xy = np.array([x[peak_ids[0]], y[peak_ids[0]]]).T;
      dist_h = np.linalg.norm(xy - head_tail_hint[0], axis = 1);
      dist_t = np.linalg.norm(xy - head_tail_hint[1], axis = 1);
      
      #closest point on contour to previous missing head/tail:
      xy = np.array([x, y]).T;   
      if dist_h <= dist_t:
        dist = np.linalg.norm(xy - head_tail_hint[1], axis = 1);          
        i_h = peak_ids[0]; 
        i_t = np.argmin(dist);
        if i_h == i_t:
          dist[i_t] = np.inf;
          i_t = np.argmin(dist);        
        imax = [i_h, i_t];  
      else:
        dist = np.linalg.norm(xy - head_tail_hint[0], axis = 1);
        i_t = peak_ids[0]; 
        i_h = np.argmin(dist);
        if i_h == i_t:
          dist[i_h] = np.inf;
          i_h = np.argmin(dist);        
        imax = [i_h, i_t];  
      status += 30;
  
    else:
      # best guess is half way along the contour
      imax = np.sort(np.asarray(np.mod(peak_ids[0] + np.array([0,ncontour//2]), ncontour), dtype = int));
      status += 40
  
  else: #peaks.shape[0] == 0
    if head_tail_hint is not None:
      xy = np.array([x, y]).T;      
      dist_h = np.linalg.norm(xy - head_tail_hint[0], axis = 1);
      dist_t = np.linalg.norm(xy - head_tail_hint[1], axis = 1);
      i_h = np.argmin(dist_h);
      i_t = np.argmin(dist_t);
      if i_h == i_t:
        dist_t[i_t] = np.inf;
        i_t = np.argmin(dist_t);        
      imax = [i_h, i_t];  
      status += 50;
    else:
      imax = np.asarray(np.round([0, ncontour//2]), dtype = int);
      status += 60;
  print(imax, status)
  
  
  ### calcualte sides and midline
  if smooth_left_right is not None and smooth_head_tail != smooth_left_right:
    cinterp, u = splprep(ptsa.T, u = None, s = smooth_left_right, per = 0, k = 4) 
    #u0 = u[nextra];
    #u1 = u[-nextra-1];
    #us = np.linspace(u0, u1, ncontour+1)[:-1];
    #x, y = splev(us, cinterp, der = 0)  
  
  
  u1 = np.linspace(us[imax[0]], us[imax[1]], ncontour)
  x1, y1 =  splev(u1, cinterp, der = 0);
  left = np.vstack([x1,y1]).T;
  
  u1 = u[-nextra-1];
  du = u1-u0;
  u2 = np.linspace(us[imax[0]], us[imax[1]]-du, ncontour);
  u2[u2 < u0] += du;
  x2, y2 = splev(u2, cinterp, der = 0);
  right = np.vstack([x2,y2]).T;
  
  # midline 
  #xm = (x1 + x2) / 2; ym = (y1 + y2) / 2; # simple
  #if isinstance(nneighbours, int) and nneighbours <= 1:
  #  center,width = center_from_sides_mean(left, right,  nsamples = nsamples, with_width = True);
  #else:
  #  center, width = center_from_sides_projection(left, right, nsamples = nsamples, with_width = True, nneighbours = nneighbours);
  center, width = center_from_sides_min_projection(left, right, npoints = npoints, nsamples = ncontour, with_width = True, smooth = smooth_center, center_offset = center_offset);
  
  # worm center
  #xymintp, u = splprep(xym.T, u = None, s = 1.0, per = 0);  
  #xc, yc = splev([0.5], xymintp, der = 0)
  #xc = xc[0]; yc = yc[0];
  
  ### plotting
  if verbose:
    #print 'max k at %s' % str(imax)
    #plt.figure(11); plt.clf();
    plt.subplot(2,3,1)
    plt.imshow(image, interpolation ='nearest')
    plt.title('raw image');
    plt.subplot(2,3,2)
    plt.imshow(imgs)
    plt.title('smoothed image');
    plt.subplot(2,3,3)
    plt.imshow(imgs, cmap = 'gray')
    plt.contour(imgs, levels = [level])
    plt.title('contour dectection')
    
    #plot curvature
    plt.subplot(2,3,4)
    plt.plot(k)
    plt.scatter(imax, k[imax], c = 'r', s= 100);
    if len(peak_ids) > 0:
      plt.scatter(peak_ids, peak_values, c = 'm', s= 40);
    plt.title('curvature')
    
    # shape detection
    plt.subplot(2,3,5)
    plt.imshow(image, cmap = 'gray', interpolation = 'nearest')
    
    left1, right1 = shape_from_center_discrete(center, width);
    plt.plot(left1[:,0]  , left1[:,1]  , 'r', linewidth= 2)
    plt.plot(right1[:,0] , right1[:,1] , 'r', linewidth= 2)    
    
    
    plt.plot(left[:,0]  , left[:,1]  , 'g', linewidth= 1)
    plt.plot(right[:,0] , right[:,1] , 'y', linewidth= 1)
    plt.plot(center[:,0], center[:,1], 'b')
    
    if smooth_left_right is not None and smooth_head_tail != smooth_left_right:
      #  x, y = splev(us, cinterp, der = 0);
      plt.plot(x,y, 'm', linewidth = 1);
    

    
    # plot segments
    #for i in range(len(xm)):
    #    plt.plot([x1[i], x2[nu[i]]], [y1[i], y2[nu[i]]], 'm')
    #plot center
    n2 = (npoints-1)//2;
    plt.scatter(center[n2,0], center[n2,1], color = 'k', s = 150)
    #plt.scatter(x[imax], y[imax], s=150, color='r');
    plt.contour(imgs, levels = [level])
    plt.title('shape detection')
    
    #plot width profile    
    plt.subplot(2,3,6)
    plt.plot(width);
    plt.title('width')
    
    if isinstance(save, str):
      fig = plt.gcf();
      fig.savefig(save);
  
  ### measure features
  # points
  #pos_head = np.array([x1[0], y1[0]])
  #pos_tail = np.array([x1[-1], y1[-1]])
  #pos_center = np.array([xc, yc]);
  
  # head tail distance:
  #dist_head_tail = np.linalg.norm(pos_head-pos_tail)
  #dist_head_center = np.linalg.norm(pos_head-pos_center)
  #dist_tail_center = np.linalg.norm(pos_tail-pos_center)
  
  #average curvature
  #dcx, dcy = splev(u, xymintp, der = 1)
  #d2cx, d2cy = splev(u, xymintp, der = 2)
  #ck = (dcx * d2cy - dcy * d2cx)/np.power(dcx**2 + dcy**2, 1.5);
  #curvature_mean = np.mean(ck);
  #curvature_variation = np.sum(np.abs(ck))
  
  ### returns
  #success = pts_inner is None;
  return status, center, left, right, width



def center_from_image_skeleton(image, sigma = 1, absolute_threshold = None, threshold_factor = 0.95, npoints = 21, smooth = 0, verbose = False, save = None):
  """Detect non-self-intersecting center lines of the worm from an image using skeletonization
  
  Arguments:
    image (array): the image to detect venterline of worm from
    sigma (float or None): width of Gaussian smoothing on image, if None use raw image
    absolute_threshold (float or None): if set use this as the threshold, if None the threshold is set via Otsu
    threshold_level (float): in case the threshold is determined by Otsu multiply by this factor
    npoints (int): number of sample points along the center line
    verbose (bool): plot results
    save (str or None): save result plot to this file
  
  Returns:
    array (npointsx2): center line
    array (npointsx2): width
    array (npointsx2): left,right
  """
  
  # Note; could be extend to detect self-intersecting worm  by matching slopes along a single corsing point
  
  ### smooth image
  if sigma is not None:
    imgs = filters.gaussian_filter(np.asarray(image, float), sigma);
  else:
    imgs = image;
   
  ### get worm foreground
  if absolute_threshold is not None:
    level = absolute_threshold;
  else:
    level = threshold_factor * threshold_otsu(imgs);
  imgth = imgs < level;  
  
  ### skeletonize
  skel = skeletonize(imgth);
  
  ### convert skeleton to line 
  # Note: here we return an error in case this is not a trivial line with two endpoints
  # potentiall can extend to detect overlapping shapes etc
  x,y = np.where(skel);
  adj = skeleton_to_adjacency(skel)
  
  # find end points:
  nhs = np.array([len(v) for v in adj.values()]);
  ht = np.where(nhs == 1)[0];
  
  if len(ht) != 2:
    if verbose:
      plt.imshow(imgs);
      plt.scatter(y,x, s = 10, c = 'r');
    raise RuntimeError('skeletonization detected %d possible heat/tail locations' % len(ht));
  
  e = adj.keys()[ht[1]];  
  p = adj.keys()[ht[0]];  
  xy = np.zeros((len(adj), 2));
  xy[0] = p;
  i = 1;
  p0 = p;
  while p != e:
    neighbrs = adj[p];
    if neighbrs[0] != p0:
      p0, p = p, neighbrs[0];
    else:
      p0, p = p, neighbrs[1];
    xy[i] = p; i+=1;
  xy = xy[:,::-1];
  
  #Note: could add head tail positions detected in contour  and width detection here
  
  ### resample and plot result  
  if verbose:
    plt.imshow(imgs)
    plt.plot(xy[:,0], xy[:,1], 'y')    
    
  xy = resample_curve(xy, npoints = npoints, smooth = smooth)
  
  if verbose:
    plt.plot(xy[:,0], xy[:,1], 'r')
  
  return xy;

 
def skeleton_from_image_discrete(image, sigma = 1, absolute_threshold = None, threshold_factor = 0.95, with_head_tail = False, verbose = False):
  """Detect skeleton points of wormshape in image
  
  Arguments:
    image (array): the image to detect venterline of worm from
    sigma (float or None): width of Gaussian smoothing on image, if None use raw image
    absolute_threshold (float or None): if set use this as the threshold, if None the threshold is set via Otsu
    threshold_level (float): in case the threshold is determined by Otsu multiply by this factor
    verbose (bool): plot results
  
  Returns:
    array (nx2): unsorted skeleton points
  """
  ### smooth image
  if sigma is not None:
    imgs = filters.gaussian_filter(np.asarray(image, float), sigma);
  else:
    imgs = image;
   
  ### get worm foreground
  if absolute_threshold is not None:
    level = absolute_threshold;
  else:
    level = threshold_factor * threshold_otsu(imgs);
  imgth = imgs < level;  
  
  ### skeletonize
  skel = skeletonize(imgth);
  y,x = np.where(skel);
  
  if verbose:
    plt.imshow(imgth, interpolation = 'none');
    plt.scatter(x,y,c = 'k', s = 40);
  
  if with_head_tail:
    # find end points:
    adj = skeleton_to_adjacency(skel);
    nhs = np.array([len(v) for v in adj.values()]);
    ht = np.where(nhs == 1)[0];
    
    if verbose:
      xy = np.vstack([x,y]).T;
      if ht.shape[0] > 0:
        xyht = xy[ht];
        plt.scatter(xyht[:,0], xyht[:,1], s = 60, c = 'r');
    
    return np.vstack([x,y]).T, ht;
  else:
    return np.vstack([x,y]).T;


def contours_from_image(image, sigma = 1, absolute_threshold = None, threshold_factor = 0.95, 
                       verbose = False, save = None):
  """Detect the boundary contours of the worm 
  
  Arguments:
    image (array): the image to detect worm from
    sigma (float or None): width of Gaussian smoothing on image, if None use raw image
    absolute_threshold (float or None): if set use this as the threshold, if None the threshold is set via Otsu
    threshold_level (float): in case the threshold is determined by Otsu multiply by this factor
    verbose (bool): plot results
    save (str or None): save result plot to this file
  
  Returns:
    tuple of arrays (npointsx2): outer and potentially inner contour lines
  """
  
  ### smooth image
  if sigma is not None:
    imgs = filters.gaussian_filter(np.asarray(image, float), sigma);
  else:
    imgs = image;
   
  ### get contours
  if absolute_threshold is not None:
    level = absolute_threshold;
  else:
    level = threshold_factor * threshold_otsu(imgs);
  
  cts = detect_contour(imgs, level);
  
  if len(cts) == 0:
    if verbose:
      print("Could not detect worm: No countours found!");
    #outer, inner = None, None;
    cts = ();
  elif len(cts) == 1:
    #outer, inner = cts[0], None;    
    cts = cts;
  elif len(cts) == 2:
    if cts[0].shape[0] < cts[1].shape[0]:
      i,o = 0,1;
    else:
      i,o = 1,0;
    if inside_polygon(cts[i], cts[o][0,:]):
      i,o = o,i;
    #outer, inner = cts[o], cts[i];
    cts = (cts[o], cts[i]);
  else:
    if verbose:
      print("Found %d countours!" % len(cts));
    #sort by length as a guess for outer contour
    l = [len(c) for c in cts];
    cts = tuple([cts[i] for i in np.argsort(l)]);
  
  ### plotting
  if verbose:    
    #plt.figure(11); plt.clf();
    plt.subplot(1,3,1)
    plt.imshow(image, interpolation ='nearest')
    plt.title('raw image');
    plt.subplot(1,3,2)
    plt.imshow(imgs)
    plt.title('smoothed image');
    plt.subplot(1,3,3)
    plt.imshow(imgs, cmap = 'gray') 
    for c in cts:
      plt.plot(c[:,0], c[:,1])
    plt.title('contour dectection')
        
    if isinstance(save, str):
      fig = plt.gcf();
      fig.savefig(save);
  
  return cts


def contours_from_shape_discrete(left, right):
  """Convert the worm shape to contours
  
  Arguments:
    left, right (nx2 arrays): left and right side of the worm
    
  Returns
    nx2: contours of the worm
  """
  poly = geom.Polygon(np.vstack([left, right[::-1,:]]));
  poly = poly.buffer(0)
  bdr = poly.boundary;
  if isinstance(bdr, geom.multilinestring.MultiLineString):
    cts = [];
    for b in bdr:
      x,y = b.xy;
      cts.append(np.vstack([x,y]).T);
  else: # no self intersections
    x,y = bdr.xy;
    cts = np.vstack([x,y]).T;
  
  return tuple(cts)  


def curvature_from_contour(contour,ncontour = all, smooth = 1.0):
  if isinstance(contour, Curve):
    contour = contour.values;
  
  # only detect heads on outer contour as ts very unlikely tofind it in inner one
  if ncontour is all:
    ncontour = contour.shape[0];
  
  cinterp, u = splprep(contour.T, u = None, s = smooth, per = 1) 
  us = np.linspace(u.min(), u.max(), ncontour)
  x, y = splev(us[:-1], cinterp, der = 0)

  ### curvature along the points
  dx, dy = splev(us[:-1], cinterp, der = 1)
  d2x, d2y = splev(us[:-1], cinterp, der = 2)
  k = (dx * d2y - dy * d2x)/np.power(dx**2 + dy**2, 1.5);
  
  return k;
  

def head_tail_from_contour_discrete(contour, delta = 0.3, max_curvature = -0.5, with_index = False,
                                    verbose = False, save = None, image = None):
  """Detect candidates for head an tail positions along a contour
  
  Arguments:
    contours (Curve or nx2 array): contour as curve or points (assumed to be closed countour[0] = contour[-1])
    delta (float): min height of peak in curvature to detect the head
    max_curvature (float or None): the peak should have at least a curvature less than this
    with_index (bool): return with indices of high curvature points
    verbose (bool): plot results
    save (str or None): save result plot to this file
    image (array): optional image for plotting
  
  Returns:
    nx2 arrays: potential positions for the head and tail
  """
  
  if isinstance(contour, Curve):
    contour = contour.values;
  
  # onlt detect heads on outer contour as ts very unlikely tofind it in inner one
  #if ncontour is all:
  #  ncontour = contour.shape[0];
  
  #cinterp, u = splprep(contour.T, u = None, s = smooth, per = 1) 
  #us = np.linspace(u.min(), u.max(), ncontour)
  #x, y = splev(us[:-1], cinterp, der = 0)

  ### curvature along the points
  #dx, dy = splev(us[:-1], cinterp, der = 1)
  #d2x, d2y = splev(us[:-1], cinterp, der = 2)
  #k = (dx * d2y - dy * d2x)/np.power(dx**2 + dy**2, 1.5);

  ### curvature as angle between subsequent segments
  
  #vectors along center line
  xyvec = np.diff(np.vstack([contour, contour[1]]), axis = 0);
  
  k = np.arctan2(xyvec[:-1,0], xyvec[:-1,1]) - np.arctan2(xyvec[1:,0], xyvec[1:,1]);
  k = np.mod(k + np.pi, 2 * np.pi) - np.pi;
  
  k = np.hstack([k[-1], k]);
  
  
  print(k.shape)
  print(contour.shape)
  
  ### find tail / head via peak detection
  #pad k to detect peaks on both sides
  nextra = 20;
  kk = -k; # negative curvature peaks are heads/tails
  kk = np.hstack([kk,kk[:nextra]]);
  kpeaks = find_peaks(kk, delta = delta);
  #print peaks.shape
  if kpeaks.shape[0] > 0:  
    kpeaks = kpeaks[kpeaks[:,0] < k.shape[0],:];
    idx = np.asarray(kpeaks[:,0], dtype = int);
    
    if max_curvature is not None:
      idk = -kk[idx] < max_curvature;
      kpeaks = kpeaks[idk];
      idx = idx[idk];
  
    print(kk[idx]);
    peaks = np.vstack([contour[idx,0], contour[idx,1]]).T;
  else:
    peaks = np.zeros((0,2));
    idx = np.zeros(0,dtype = int);
    
  ### plotting
  if verbose:
    #plt.figure(11); plt.clf();
    if image is not None:
      plt.subplot(1,2,1)
      plt.imshow(image, cmap = 'gray') 
      plt.plot(contour[:,0], contour[:,1], 'r')
      plt.plot(contour[0,0], contour[0,1], '.g', markersize = 16)
      if len(peaks)> 0:
        plt.scatter(peaks[:,0], peaks[:,1], c = 'm', s = 20);
      plt.title('contour dectection')
      plt.subplot(1,2,2);
    
    plt.plot(k)
    #plt.scatter(imax, k[imax], c = 'r', s= 100);
    if kpeaks.shape[0] > 0:
      plt.scatter(kpeaks[:,0], -kpeaks[:,1], c = 'm', s= 40);
    plt.title('curvature')
    
    if isinstance(save, str):
      fig = plt.gcf();
      fig.savefig(save);
  
  if with_index:
    return peaks, idx
  else:
    return peaks;


def normals_from_contour_discrete(contour):
  """Returns normal vectors along the contour
  
  Arguments:
    contours (Curve or 2xn array): contour
  
  Returns:
    nx2 array: normals corresponding to the contours
    
  Note:
    Assumes closed contour with contour[0]==contour[-1] for all i.
  """
  if isinstance(contour, Curve):
    contour = contour.values;
  
  if not np.allclose(contour[0], contour[-1]):
     raise ValueError('contour not closed!');
  
  #vectors along contour line
  centervec = np.diff(contour, axis = 0);
  
  # absolute orientation
  t0 = np.array([1,0], dtype = float); #vertical reference
  t1 = centervec[0];
  orientation = np.mod(np.arctan2(t0[0], t0[1]) - np.arctan2(t1[0], t1[1]) + np.pi, 2 * np.pi) - np.pi;
    
  # discrete thetas (no rescaling)
  theta = np.arctan2(centervec[:-1,0], centervec[:-1,1]) - np.arctan2(centervec[1:,0], centervec[1:,1]);
  theta = np.mod(theta + np.pi, 2 * np.pi) - np.pi;
  theta = np.hstack([0, theta]);
  
  # integrate and rotate by pi/2 / half angle at point
  itheta = np.cumsum(theta);
  itheta += np.pi/2 + orientation;
  itheta -= theta / 2;
  itheta[0] -= theta[-1] / 2;
  
  #ithetas.append(itheta);
  return np.vstack([np.cos(itheta), np.sin(itheta)]).T;
  


def self_occlusions_from_shape_discrete(left, right, margin = 0.01, with_bools = True, with_index = False, with_points = False):
  """Returns points of the shape that are occulded by the worm itself
  
  Arguments:
    left,right (nx2 array): sides of the worm
    margin (float): margin by which to reduce width in order to detect real insiders (small fraction of thw width)
    with_bools (bool): if True return two array's indicating which points are not occluded
    with_index (bool): if True return two arrays with indices of which points are occluded
    with_points (bool): if True return points on left and right curves that are occluded
    
  Returns
    array, array: left,right array of bools indicating valid non-occluded points
    array, array: left, right indices of occluded points
    array, array: left,right occluded points
  """
  
  poly = geom.Polygon(np.vstack([left, right[::-1,:]]));
  poly = poly.buffer(-margin);
  
  inleft = [poly.contains(geom.Point(xy)) for xy in left];
  inright = [poly.contains(geom.Point(xy)) for xy in right]; 
  
  res = [];
  if with_bools:
    res.append(np.logical_not(inleft)); res.append(np.logical_not(inright));
  if with_index:
    res.append(np.where(inleft)[0]);
    res.append(np.where(inright)[0]);  
  if with_points:
    res.append(left[inleft]);
    res.append(right[inright]);
  
  return tuple(res);

  
def distance_shape_to_contour_discrete(left, right, normals, contour, 
                                       search_radius = [10,20], min_alignment = None, 
                                       match_head_tail = None, 
                                       verbose = False):
  """Find distances of points on shape to positions on the contour
  
  Arguments:
    left,right (Curve or nx2 array): shape 
    normals (nx2 array): normals for the shape
    contour (nx2 array): the contour curve
    search_radius (float or array): the search radius to check for points
    min_alignment (float or None): if not None also ensure the normals are aligned
    verbose (bool): plot results
  """
  if not isinstance(contour, Curve):
    contour = Curve(contour);
  
  search_radius =  np.array(search_radius);
  if search_radius.shape[0] < 2:
    search_radius = np.hstack([search_radius]*2);

  if match_head_tail is not None:
    lleft = left[1:-1];
    rright = right[1:-1];
    normals = normals[1:-1];
  else:
    lleft = left;
    rright = right;

  # normal lines along which to find intersections
  npts = lleft.shape[0];
  left_start = lleft - search_radius[0] * normals;
  left_end   = lleft + search_radius[1] * normals;
  right_start = rright + search_radius[0] * normals;
  right_end   = rright - search_radius[1] * normals;

  distances_left  = np.zeros(npts);
  distances_right = np.zeros(npts);
  
  intersection_pts_left  = np.zeros((npts,2));
  intersection_pts_right = np.zeros((npts,2));
  
  for i in range(npts):
    #intersection points
    xy,ii,ij,pi,pj = contour.intersections(np.vstack([left_start[i], left_end[i]]),  with_xy = True, with_indices = True, with_points = True);
    #xy,ii,ij,pi,pj = curve_intersections_discrete(np.vstack([left_start[i], left_end[i]]), contour);

    #occuled points:
    if len(ii) == 0:
      distances_left[i] = np.nan;
      intersection_pts_left[i,:] = np.nan;
      continue
    
    if min_alignment is not None:
      cntnrmls = contour.normals(points = pi, normalize = True);
            
      if verbose:
        for pt, nm in zip(xy, cntnrmls):
          pt2 = pt + 5 * nm;
          plt.plot([pt[0], pt2[0]],[pt[1], pt2[1]], 'k');      
      
      algnmt = np.dot(cntnrmls, normals[i]);
      aligned = algnmt >= min_alignment;
      if np.any(aligned):
        xy = xy[aligned];
        ii = ii[aligned];
        ij = ij[aligned];
        pi = pi[aligned];
        pj = pj[aligned];
      else:
        distances_left[i] = np.nan;
        intersection_pts_left[i,:] = np.nan;
        continue
    
    dd = np.linalg.norm(lleft[i] - xy,axis =1);
    minidx = np.argmin(dd);
    distances_left[i] = dd[minidx];
    intersection_pts_left[i,:] = xy[minidx];

  
  for i in range(npts):
    #intersection points
    xy,ii,ij,pi,pj = contour.intersections(np.vstack([right_start[i], right_end[i]]),  with_xy = True, with_indices = True, with_points = True);

       
    #occuled points:
    if len(ii) == 0:
      distances_right[i] = np.nan;
      intersection_pts_right[i,:] = np.nan;
      continue
    
    if min_alignment is not None:
      cntnrmls = contour.normals(points = pi, normalize = True);
      
      algnmt = np.dot(cntnrmls, -normals[i]);
      #print algnmt, npts, i;
      aligned = algnmt >= min_alignment;
      if np.any(aligned):
        xy = xy[aligned];
        ii = ii[aligned];
        ij = ij[aligned];
        pi = pi[aligned];
        pj = pj[aligned];
        
        if verbose:
          for pt, nm in zip(xy, cntnrmls[aligned]):
            pt2 = pt + 5 * nm;
            plt.plot([pt[0], pt2[0]],[pt[1], pt2[1]], 'k');        
        
      else:
        distances_right[i] = np.nan;
        intersection_pts_right[i,:] = np.nan;
        continue
    
    dd = np.linalg.norm(rright[i] - xy,axis =1);
    minidx = np.argmin(dd);
    distances_right[i] = dd[minidx];
    intersection_pts_right[i,:] = xy[minidx];
  
  if match_head_tail is not None:
    if len(match_head_tail) > 0:
      head = left[0];
      tail= left[-1];
      dists_head = np.linalg.norm(head - match_head_tail, axis = 1);
      dists_tail = np.linalg.norm(tail - match_head_tail, axis = 1);
      head_match = np.argmin(dists_head);
      tail_match = np.argmin(dists_tail);
      distance_head = dists_head[head_match];
      distance_tail = dists_tail[tail_match];
      if head_match == tail_match:
        if dists_head[head_match] <= dists_tail[tail_match]:
          if len(dists_tail) <= 1:
            distance_tail = np.nan;
            tail_match = None;
          else:
            dists_tail[tail_match] = dists_tail.max() + 1;
            tail_match = np.argmin(dists_tail);
            distance_tail = dists_tail[tail_match];
        else:
          if len(dists_head) <= 1:
            distance_head = np.nan;
            head_match = None;
          else:
            dists_head[head_match] = dists_head.max() + 1;
            head_match = np.argmin(dists_head);
            dists_head = dists_tail[head_match];
    else:
      distance_tail = np.nan;
      distance_head = np.nan;
      tail_match = None;
      head_match = None;
  
  if verbose:
      contour.plot(with_points = False);
      occ = np.where(distances_left == np.nan)[0];
      for i in range(npts):
        plt.plot([left_start[i,0], left_end[i,0]], [left_start[i,1], left_end[i,1]], 'r');
        plt.plot([right_start[i,0],right_end[i,0]], [right_start[i,1], right_end[i,1]], 'b');
        plt.scatter(lleft[:,0],lleft[:,1], c = 'r', s = 100)
        plt.scatter(rright[:,0],rright[:,1], c = 'b', s = 100)
        plt.scatter(lleft[occ,0],lleft[occ,1], c = 'k', s = 60)
        plt.scatter(rright[occ,0],rright[occ,1], c = 'k', s = 60)
        plt.scatter(intersection_pts_left[:,0], intersection_pts_left[:,1], c = 'r', s = 40);
        plt.scatter(intersection_pts_right[:,0], intersection_pts_right[:,1], c = 'b', s = 40);
      plt.axis('equal')

      if match_head_tail is not None:
        plt.scatter(match_head_tail[:,0], match_head_tail[:,1], c = 'y', s = 100);
        if head_match is not None:
          head= left[0]; match_xy = match_head_tail[head_match];
          plt.plot([match_xy[0], head[0]], [match_xy[1], head[1]], c = 'k');
          plt.scatter(head[0], head[1], c = 'purple', s = 100);
        if tail_match is not None:
          tail= left[-1]; match_xy = match_head_tail[tail_match];
          plt.plot([match_xy[0], tail[0]], [match_xy[1], tail[1]], c = 'k');
          plt.scatter(tail[0], tail[1], c = 'orange', s = 100);

          
        
  if match_head_tail is not None:
    return distances_left, intersection_pts_left, distances_right, intersection_pts_right, distance_head, head_match, distance_tail, tail_match
  else:
    return distances_left, intersection_pts_left, distances_right, intersection_pts_right



##############################################################################
### Tests

def test():
  from importlib import reload
  import numpy as np
  import matplotlib.pyplot as plt
  import worm.geometry as wgeo
  from interpolation.resampling import resample as resample_curve
  reload(wgeo)
  
  ### Center form sides
  t = np.linspace(0,10,50);
  aline = np.vstack([t, np.sin(t)+0.5]).T;
  aline[0] = [0,0];
  bline = np.vstack([t, np.sin(t)]).T;
  aline[0] = bline[0];  
  aline[-1] = bline[-1];
  aline = resample_curve(aline, npoints = 50);
  bline = resample_curve(bline, npoints = 50);
  
  cline = wgeo.center_from_sides(aline, bline, nsamples = 50, npoints = 50, smooth = 0.1, resample = True, method = 'projection');
  
  plt.figure(1); plt.clf();
  plt.plot(aline[:,0], aline[:,1]);
  plt.plot(bline[:,0], bline[:,1]);
  plt.plot(cline[:,0], cline[:,1]);

  reload(wgeo)
  cline = wgeo.center_from_sides_erosion(aline, bline, erode = 0.05, nsamples = 50, npoints = 50, smooth = 0.1, resample = True);
  
  plt.figure(2); plt.clf();
  plt.plot(aline[:,0], aline[:,1]);
  plt.plot(bline[:,0], bline[:,1]);
  plt.plot(cline[:,0], cline[:,1]);

  
  ### Image analysis  
  reload(wgeo)
  import analysis.experiment as exp;
  img = exp.load_img(t = 500000);
  
  plt.figure(1); plt.clf();
  wgeo.shape_from_image(img, npoints = 25, verbose = True)
  
  
  ### Contour detection
  reload(wgeo)
  import analysis.experiment as exp;
  i = 25620;
  i += 1;
  img = exp.load_img(t = 500000+i);
  #plt.figure(1); plt.clf();
  #plt.imshow(img);
  cts = wgeo.contour_from_image(img, verbose = True);
  
  reload(wgeo)
  cts = wgeo.contour_from_image(img, verbose = False);
  wgeo.head_tail_from_contours(cts, delta = 0.3, smooth = 1.0, verbose = True, image = img);
  
  reload(wgeo)
  cts = wgeo.contour_from_image(img, verbose = False);
  cts = tuple([resample_curve(c, npoints = 50) for c in cts]);
  nrmls = wgeo.normals_from_contours(cts);
  plt.figure(50); plt.clf();
  plt.imshow(img);
  for c,n in zip(cts,nrmls):
    plt.plot(c[:,0], c[:,1]);
    plt.scatter(c[:,0], c[:,1])
    for ci,ni in zip(c,n):
      cp = np.vstack([ci, ci+5*ni]);
      plt.plot(cp[:,0], cp[:,1], 'k');
  plt.axis('equal')
    
  
  ### Self occlusions
  import worm.model as wm;
  from importlib import reload
  reload(wgeo)
  nn = 20;
  w = wm.WormModel(theta = np.hstack([np.linspace(0.1, 0.8, nn)*13, 13* np.linspace(0.9, 0.1, nn+1)]) , length = 150);
  left, right, center, normals, width = w.shape(with_center=True, with_normals=True, with_width=True);
  
  plt.figure(1); plt.clf();
  w.plot()
  
  ocl,ocr = wgeo.self_occlusions_from_center_discrete(center, width, margin = 0.01, normals = normals, left = left, right = right, shape = True, as_index = True);
  pts = left[ocl];
  plt.scatter(pts[:,0], pts[:,1], c ='m', s = 40);
  pts = right[ocr];
  plt.scatter(pts[:,0], pts[:,1], c ='m', s = 40);
  
  occ = wgeo.self_occlusions_from_center_discrete(center, width, margin = 0.01, normals = normals, left = left, right = right, shape = False, as_index = True);
  pts = center[occ];
  plt.scatter(pts[:,0], pts[:,1], c ='b', s = 40);
  plt.axis('equal')
  
  
  
  ### Distance to a contour 
  import numpy as np
  import matplotlib.pyplot as plt
  import worm.model as wm;
  import worm.geometry as wgeo
  reload(wgeo); reload(wm);

  import analysis.experiment as exp
  import scipy.ndimage.filters as filters
  from interpolation.curve import Curve
  from interpolation.resampling import resample as resample_curve

  # load image
  img = exp.load_img(wid = 80, t= 500000);  
  imgs = filters.gaussian_filter(np.asarray(img, float), 1.0);

  w = wm.WormModel(npoints = 21);  
  w.from_image(img, verbose = True);

  plt.figure(1); plt.clf();
  plt.subplot(1,2,1)
  w.plot(image = imgs)

  w.rotate(0.2);
  plt.subplot(1,2,2);
  w.plot(image = imgs);
  
  
  cntr = wgeo.contour_from_image(imgs, sigma = 1, absolute_threshold = None, threshold_factor = 0.9, 
                            verbose = True, save = None);
  
  cntr = resample_curve(cntr[0], 100);
  contour = Curve(cntr, nparameter = 50);
  
  plt.figure(1); plt.clf();
  contour.plot()
  plt.plot(cntr[:,0], cntr[:,1], 'o')
  
  left,right,normals = w.shape(with_normals=True);  
  
  reload(wgeo); reload(wm);
  plt.figure(5); plt.clf();
  plt.subplot(1,2,1);
  dl, xyl, dr, xyr = wgeo.distance_shape_to_contour_discrete(left,right,normals,contour,search_radius=[5,20], verbose = True, min_alignment=0)
  plt.title('distance detection')
  plt.subplot(1,2,2);
  plt.plot(dl, 'g');
  plt.plot(dr, 'm');
  plt.title('distances');
  
  
  
  ### Head tail detection
  import numpy as np
  import matplotlib.pyplot as plt
  import worm.model as wm;
  import worm.geometry as wgeo
  reload(wgeo); reload(wm);

  import analysis.experiment as exp
  import scipy.ndimage.filters as filters
  from interpolation.curve import Curve
  from interpolation.resampling import resample as resample_curve

  # load image
  img = exp.load_img(wid = 80, t= 500000);  
  imgs = filters.gaussian_filter(np.asarray(img, float), 1.0);

  w = wm.WormModel(nparameter = 10);  
  w.from_image(img, verbose = True);

  plt.figure(1); plt.clf();
  plt.subplot(1,2,1)
  w.plot(image = imgs)
  plt.subplot(1,2,2);
  cntrs = wgeo.contour_from_image(imgs, sigma = 1, absolute_threshold = None, threshold_factor = 0.9, 
                            verbose = True, save = None);
  cntr = resample_curve(cntrs[0], 100);
  contour = Curve(cntr, nparameter = 50);                        
                        
                        
  plt.figure(2); plt.clf();
  head_tail_xy = wgeo.head_tail_from_contour(cntrs, ncontour = all, delta = 0.3, smooth = 1.0, with_index = False,
                              verbose = True, save = None, image = imgs);
  
  
  left,right,normals = w.shape(with_normals=True);  
  plt.figure(3); plt.clf()
  reload(wgeo)
  res = wgeo.distance_shape_to_contour_discrete(left,right,normals,contour,
                                                search_radius=[5,20], min_alignment=0, match_head_tail=head_tail_xy,
                                                verbose = True);
 

  
 
if __name__ == "__main__":
  test_theta();
  test();
