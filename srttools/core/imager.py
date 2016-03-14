"""Produce calibrated light curves.

``SDTimage`` is a script that, given a list of cross scans composing an
on-the-fly map, is able to calculate the map and save it in FITS format after
cleaning the data.
"""
from __future__ import (absolute_import, unicode_literals, division,
                        print_function)

from .scan import Scan, chan_re, list_scans
from .read_config import read_config, get_config_file, sample_config_file
import numpy as np
from astropy import wcs
from astropy.table import Table, vstack
import astropy.io.fits as fits
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

from .fit import linear_fun
from .interactive_filter import select_data
from .calibration import CalibratorTable

import sys
import warnings
import logging
import traceback


class ScanSet(Table):
    """Class containing a set of scans."""

    def __init__(self, data=None, norefilt=True, config_file=None,
                 freqsplat=None, **kwargs):
        """Initialize a ScanSet object."""
        self.norefilt = norefilt
        self.freqsplat = freqsplat

        if isinstance(data, Table):
            Table.__init__(self, data, **kwargs)
            if config_file is not None:
                config = read_config(config_file)
                self.meta.update(config)

            self.create_wcs()
        else:  # data is a config file
            config_file = data
            config = read_config(config_file)

            scan_list = \
                self.list_scans(config['datadir'],
                                config['list_of_directories'])

            scan_list.sort()
            # nscans = len(scan_list)

            tables = []

            for i_s, s in self.load_scans(scan_list,
                                          freqsplat=freqsplat, **kwargs):

                if 'FLAG' in s.meta.keys() and s.meta['FLAG']:
                    continue
                s['Scan_id'] = i_s + np.zeros(len(s['time']), dtype=np.long)

                tables.append(s)

            scan_table = Table(vstack(tables))

            Table.__init__(self, scan_table)
            self.meta['scan_list'] = scan_list
            self.meta.update(config)
            self.meta['config_file'] = get_config_file()

            self.meta['scan_list'] = np.array(self.meta['scan_list'],
                                              dtype='S')
            self.analyze_coordinates(altaz=False)
            self.analyze_coordinates(altaz=True)

            self.convert_coordinates()

        self.chan_columns = np.array([i for i in self.columns
                                      if chan_re.match(i)])
        self.current = None

    def analyze_coordinates(self, altaz=False):
        """Save statistical information on coordinates."""
        if altaz:
            hor, ver = 'az', 'el'
        else:
            hor, ver = 'ra', 'dec'

        allhor = self[hor]
        allver = self[ver]

        self.meta['mean_' + hor] = np.mean(allhor)
        self.meta['mean_' + ver] = np.mean(allver)
        self.meta['min_' + hor] = np.min(allhor)
        self.meta['min_' + ver] = np.min(allver)
        self.meta['max_' + hor] = np.max(allhor)
        self.meta['max_' + ver] = np.max(allver)

    def list_scans(self, datadir, dirlist):
        """List all scans contained in the directory listed in config."""
        return list_scans(datadir, dirlist)

    def load_scans(self, scan_list, freqsplat=None, **kwargs):
        """Load the scans in the list one by ones."""
        nscan = len(scan_list)
        for i, f in enumerate(scan_list):
            print("{}/{}".format(i + 1, nscan), end="\r")
            try:
                s = Scan(f, norefilt=self.norefilt, freqsplat=freqsplat,
                         **kwargs)
                yield i, s
            except KeyError as e:
                warnings.warn("Error while processing {}: {}".format(f,
                                                                     str(e)))
            except Exception as e:
                traceback.print_exc()
                warnings.warn("Error while processing {}: {}".format(f,
                                                                     str(e)))

    def get_coordinates(self, altaz=False):
        """Give the coordinates as pairs of RA, DEC."""
        if altaz:
            return np.array(np.dstack([self['az'],
                                       self['el']]))
        else:
            return np.array(np.dstack([self['ra'],
                                       self['dec']]))

    def create_wcs(self, altaz=False):
        """Create a wcs object from the pointing information."""
        if altaz:
            hor, ver = 'az', 'el'
        else:
            hor, ver = 'ra', 'dec'
        npix = np.array(self.meta['npix'])
        self.wcs = wcs.WCS(naxis=2)

        self.wcs.wcs.crpix = npix / 2
        delta_hor = self.meta['max_' + hor] - self.meta['min_' + hor]
        delta_ver = self.meta['max_' + ver] - self.meta['min_' + ver]

        if not hasattr(self.meta, 'reference_' + hor):
            self.meta['reference_' + hor] = self.meta['mean_' + hor]
        if not hasattr(self.meta, 'reference_' + ver):
            self.meta['reference_' + ver] = self.meta['mean_' + ver]

        # TODO: check consistency of units
        # Here I'm assuming all angles are radians
        crval = np.array([self.meta['reference_' + hor],
                          self.meta['reference_' + ver]])
        self.wcs.wcs.crval = np.degrees(crval)

        cdelt = np.array([-delta_hor / npix[0],
                          delta_ver / npix[1]])
        self.wcs.wcs.cdelt = np.degrees(cdelt)

        self.wcs.wcs.ctype = \
            ["RA---{}".format(self.meta['projection']),
             "DEC--{}".format(self.meta['projection'])]

#    def scrunch_channels(self, feeds=None, polarizations=None,
#                         chan_names=None):
#        """Scrunch channels and reduce their number.
#
#        POLARIZATIONS NOT IMPLEMENTED YET!
#        2-D lists of channels NOT IMPLEMENTED YET!
#
#        feed and polarization filters can be given as:
#
#        None:          all channels are to be summed in one
#        list of chans: channels in this list are summed, the others are
#                       deleted only one channel remains
#        2-d array:     the channels arr[0, :] will go to chan 0, arr[1, :] to
#                       chan 1, and so on.
#
#        At the end of the process, all channels have been eliminated but the
#        ones selected.
#        The axis-1 length of feeds and polarizations MUST be the same, unless
#        one of them is None.
#        """
#        # TODO: Implement polarizations
#        # TODO: Implement 2-d arrays
#
#        allfeeds = np.array([self[ch + '_feed'][0]
#                             for ch in self.chan_columns])
#        if feeds is None:
#            feeds = list(set(allfeeds))
#
#        feed_mask = np.in1d(allfeeds, feeds)

    def convert_coordinates(self, altaz=False):
        """Convert the coordinates from sky to pixel."""
        if altaz:
            hor, ver = 'az', 'el'
        else:
            hor, ver = 'ra', 'dec'
        self.create_wcs(altaz)

        self['x'] = np.zeros_like(self[hor])
        self['y'] = np.zeros_like(self[ver])
        coords = np.degrees(self.get_coordinates())
        for f in range(len(self[hor][0, :])):
            pixcrd = self.wcs.wcs_world2pix(coords[:, f], 0)

            self['x'][:, f] = pixcrd[:, 0]
            self['y'][:, f] = pixcrd[:, 1]

    def calculate_images(self, scrunch=False, no_offsets=False, altaz=False,
                         calibration=None):
        """Obtain image from all scans.

        scrunch:         sum all channels
        no_offsets:      use positions from feed 0 for all feeds.
        """
        images = {}
        # xbins = np.linspace(np.min(self['x']),
        #                     np.max(self['x']),
        #                     self.meta['npix'][0] + 1)
        # ybins = np.linspace(np.min(self['y']),
        #                     np.max(self['y']),
        #                     self.meta['npix'][1] + 1)
        xbins = np.linspace(0,
                            self.meta['npix'][0],
                            self.meta['npix'][0] + 1)
        ybins = np.linspace(0,
                            self.meta['npix'][1],
                            self.meta['npix'][1] + 1)

        total_expo = 0
        total_img = 0
        total_sdev = 0
        for ch in self.chan_columns:
            feeds = self[ch+'_feed']
            allfeeds = list(set(feeds))
            assert len(allfeeds) == 1, 'Feeds are mixed up in channels'
            if no_offsets:
                feed = 0
            else:
                feed = feeds[0]

            if '{}-filt'.format(ch) in self.keys():
                good = self['{}-filt'.format(ch)]
            else:
                good = np.ones(len(self[ch]), dtype=bool)

            expomap, _, _ = np.histogram2d(self['x'][:, feed][good],
                                           self['y'][:, feed][good],
                                           bins=[xbins, ybins])

            img, _, _ = np.histogram2d(self['x'][:, feed][good],
                                       self['y'][:, feed][good],
                                       bins=[xbins, ybins],
                                       weights=self[ch][good])
            img_sq, _, _ = np.histogram2d(self['x'][:, feed][good],
                                          self['y'][:, feed][good],
                                          bins=[xbins, ybins],
                                          weights=self[ch][good] ** 2)

            good = expomap > 0
            mean = img.copy()
            total_img += mean.T
            mean[good] /= expomap[good]
            # For Numpy vs FITS image conventions...
            images[ch] = mean.T
            img_sdev = img_sq
            total_sdev += img_sdev.T
            img_sdev[good] = img_sdev[good] / expomap[good] - mean[good] ** 2

            images['{}-Sdev'.format(ch)] = img_sdev.T
            total_expo += expomap.T

        self.images = images
        if calibration is not None:
            self.calibrate_images(calibration)

        if scrunch:
            # Filter the part of the image whose value of exposure is higher
            # than the 10% percentile (avoid underexposed parts)
            good = total_expo > np.percentile(total_expo, 10)
            bad = np.logical_not(good)
            total_img[bad] = 0
            total_sdev[bad] = 0
            total_img[good] /= total_expo[good]
            total_sdev[good] = total_sdev[good] / total_expo[good] - \
                total_img[good] ** 2

            images = {self.chan_columns[0]: total_img,
                      '{}-Sdev'.format(self.chan_columns[0]): total_sdev,
                      '{}-EXPO'.format(self.chan_columns[0]): total_expo}

        return images

    def calibrate_images(self, calibration):
        """Calibrate the images."""
        if not hasattr(self, 'images'):
            self.calculate_images()

        caltable = CalibratorTable().read(calibration)
        caltable.update()

        for ch in self.chan_columns:
            Jy_over_counts, Jy_over_counts_err = \
                caltable.Jy_over_counts(channel=ch)
            if np.isnan(Jy_over_counts):
                warnings.warn("The Jy/counts factor is nan")
                continue
            A = self.images[ch].copy()
            eA = self.images['{}-Sdev'.format(ch)].copy()

            self.images['{}-RAW'.format(ch)] = \
                self.images['{}'.format(ch)].copy()
            self.images['{}-Sdev-RAW'.format(ch)] = \
                self.images['{}-Sdev'.format(ch)].copy()
            bad = eA != eA
            A[bad] = 1
            eA[bad] = 0

            bad = np.logical_or(A == 0, A != A)
            A[bad] = 1
            eA[bad] = 0

            B = Jy_over_counts
            eB = Jy_over_counts_err

            C = A * Jy_over_counts

            self.images[ch] = C

            eC = C * (eA / A + eB / B)

            self.images['{}-Sdev'.format(ch)] = eC

    def interactive_display(self, ch=None, recreate=False):
        """Modify original scans from the image display."""
        from .interactive_filter import ImageSelector

        if not hasattr(self, 'images') or recreate:
            self.calculate_images()

        if ch is None:
            chs = self.chan_columns
        else:
            chs = [ch]

        for ch in chs:
            fig = plt.figure('Imageactive Display')
            gs = GridSpec(1, 2, width_ratios=(3, 2))
            ax = fig.add_subplot(gs[0])
            ax2 = fig.add_subplot(gs[1])
            imgch = ch
            sdevch = '{}-Sdev'.format(ch)
            if '{}-RAW'.format(ch) in self.images.keys():
                imgch = '{}-RAW'.format(ch)
                sdevch = '{}-Sdev-RAW'.format(ch)
            img = self.images[imgch]
            ax2.imshow(img, origin='lower',
                       vmin=np.percentile(img, 20), cmap="gnuplot2",
                       interpolation="nearest")

            img = self.images[sdevch].copy()
            self.current = ch
            bad = np.logical_or(img == 0, img != img)
            img[bad] = np.mean(img[np.logical_not(bad)])
            ImageSelector(img, ax, fun=self.rerun_scan_analysis)

    def rerun_scan_analysis(self, x, y, key):
        """Rerun the analysis of single scans."""
        logging.debug(x, y, key)
        if key == 'a':
            self.reprocess_scans_through_pixel(x, y)
        elif key == 'h':
            pass
        elif key == 'v':
            pass

    def reprocess_scans_through_pixel(self, x, y):
        """Given a pixel in the image, find all scans passing through it."""
        ch = self.current

        ra_xs, ra_ys, dec_xs, dec_ys, scan_ids, ra_masks, dec_masks, \
            vars_to_filter = \
            self.find_scans_through_pixel(x, y)

        info = select_data(ra_xs, ra_ys, masks=ra_masks,
                           xlabel="RA", title="RA")

        for sname in info.keys():
            self.update_scan(sname, scan_ids[sname], vars_to_filter[sname],
                             info[sname]['zap'],
                             info[sname]['fitpars'], info[sname]['FLAG'])

        info = select_data(dec_xs, dec_ys, masks=dec_masks, xlabel="Dec",
                           title="Dec")

        for sname in info.keys():
            self.update_scan(sname, scan_ids[sname], vars_to_filter[sname],
                             info[sname]['zap'],
                             info[sname]['fitpars'], info[sname]['FLAG'])

        self.interactive_display(ch=ch, recreate=True)

    def find_scans_through_pixel(self, x, y):
        """Find scans passing through a pixel."""
        ra_xs = {}
        ra_ys = {}
        dec_xs = {}
        dec_ys = {}
        scan_ids = {}
        ra_masks = {}
        dec_masks = {}
        vars_to_filter = {}

        ch = self.current
        feed = list(set(self[ch+'_feed']))[0]

        # Select data inside the pixel +- 1

        good_entries = \
            np.logical_and(
                np.abs(self['x'][:, feed] - x) < 1,
                np.abs(self['y'][:, feed] - y) < 1)

        sids = list(set(self['Scan_id'][good_entries]))

        for sid in sids:
            sname = self.meta['scan_list'][sid].decode()
            try:
                s = Scan(sname)
            except:
                continue
            try:
                chan_mask = s['{}-filt'.format(ch)]
            except:
                chan_mask = np.zeros_like(s[ch])

            scan_ids[sname] = sid
            ras = s['ra'][:, feed]
            decs = s['dec'][:, feed]

            z = s[ch]

            ravar = np.max(ras) - np.min(ras)
            decvar = np.max(decs) - np.min(decs)
            if ravar > decvar:
                vars_to_filter[sname] = 'ra'
                ra_xs[sname] = ras
                ra_ys[sname] = z
                ra_masks[sname] = chan_mask
            else:
                vars_to_filter[sname] = 'dec'
                dec_xs[sname] = decs
                dec_ys[sname] = z
                dec_masks[sname] = chan_mask

        return ra_xs, ra_ys, dec_xs, dec_ys, scan_ids, ra_masks, dec_masks, \
            vars_to_filter

    def update_scan(self, sname, sid, dim, zap_info, fit_info, flag_info):
        """Update a scan in the scanset after filtering."""
        ch = self.current
        feed = list(set(self[ch+'_feed']))[0]
        mask = self['Scan_id'] == sid
        try:
            s = Scan(sname)
        except:
            return

        if len(zap_info.xs) > 0:

            xs = zap_info.xs
            good = np.ones(len(s[dim]), dtype=bool)
            if len(xs) >= 2:
                intervals = list(zip(xs[:-1:2], xs[1::2]))
                for i in intervals:
                    good[np.logical_and(s[dim][:, feed] >= i[0],
                                        s[dim][:, feed] <= i[1])] = False
            s['{}-filt'.format(ch)] = good
            self['{}-filt'.format(ch)][mask] = good

        if len(fit_info) > 1:
            s[ch] -= linear_fun(s[dim][:, feed],
                                *fit_info)
        # TODO: make it channel-independent
            s.meta['backsub'] = True
            try:
                self[ch][mask][:] = s[ch]
            except:
                warnings.warn("Something while treating {}".format(sname))

                plt.figure("DEBUG")
                plt.plot(self['ra'][mask], self['dec'][mask])
                plt.show()
                raise

        # TODO: make it channel-independent
        if flag_info:
            s.meta['FLAG'] = True
            self['{}-filt'.format(ch)][mask] = np.zeros(len(s[dim]),
                                                        dtype=bool)

        s.save()

    def write(self, fname, **kwargs):
        """Set default path and call Table.write."""
        t = Table(self)
        t.write(fname, path='scanset', **kwargs)

    def save_ds9_images(self, fname=None, save_sdev=False, scrunch=False,
                        no_offsets=False, altaz=False, calibration=None):
        """Save a ds9-compatible file with one image per extension."""
        if fname is None:
            fname = self.meta['config_file'].replace('ini','fits')
        images = self.calculate_images(scrunch=scrunch, no_offsets=no_offsets,
                                       altaz=altaz, calibration=calibration)
        self.create_wcs(altaz)

        hdulist = fits.HDUList()

        header = self.wcs.to_header()

        hdu = fits.PrimaryHDU(header=header)
        hdulist.append(hdu)

        keys = list(images.keys())
        keys.sort()
        for ic, ch in enumerate(keys):
            is_sdev = ch.endswith('Sdev')

            if is_sdev and not save_sdev:
                continue

            hdu = fits.ImageHDU(images[ch], header=header, name='IMG' + ch)
            hdulist.append(hdu)

        hdulist.writeto(fname, clobber=True)


def main_imager(args=None):
    """Main function."""
    import argparse

    description = ('Load a series of scans from a config file '
                   'and produce a map.')
    parser = argparse.ArgumentParser(description=description)

    parser.add_argument("--sample-config", action='store_true', default=False,
                        help='Produce sample config file')

    parser.add_argument("-c", "--config", type=str, default=None,
                        help='Config file')

    parser.add_argument("--refilt", default=False,
                        action='store_true',
                        help='Re-run the scan filtering')

    parser.add_argument("--interactive", default=False,
                        action='store_true',
                        help='Open the interactive display')

    parser.add_argument("--calibrate", type=str, default=None,
                        help='Calibration file')

    parser.add_argument("--splat", type=str, default=None,
                        help=("Spectral scans will be scrunched into a single "
                              "channel containing data in the given frequency "
                              "range, starting from the frequency of the first"
                              " bin. E.g. '0:1000' indicates 'from the first "
                              "bin of the spectrum up to 1000 MHz above'. ':' "
                              "or 'all' for all the channels."))

    args = parser.parse_args(args)

    if args.sample_config:
        sample_config_file()
        sys.exit()

    assert args.config is not None, "Please specify the config file!"

    scanset = ScanSet(args.config, norefilt=not args.refilt,
                      freqsplat=args.splat)

    if args.interactive:
        scanset.interactive_display()
    scanset.save_ds9_images(save_sdev=True, calibration=args.calibrate)