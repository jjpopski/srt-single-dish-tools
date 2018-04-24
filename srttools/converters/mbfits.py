from astropy.io import fits
from astropy.table import Table
from astropy.time import Time
import astropy.units as u
import os
import numpy as np
from srttools.io import mkdir_p, locations, read_data_fitszilla, \
    get_chan_columns, get_channel_feed
from srttools.utils import scantype


def _copy_hdu_and_adapt_length(hdu, length):
    data = hdu.data
    columns = []
    for i, col in enumerate(data.columns):
        newvals = [data[col.name][0]] * length
        newcol = fits.Column(name=col.name, array=newvals,
                             format=col.format)
        columns.append(newcol)
    newhdu = fits.BinTableHDU.from_columns(columns)
    newhdu.header = hdu.header
    return newhdu


class MBFits_template(object):
    def __init__(self, mbfits_dir='.'):
        self.mbfits_dir = mbfits_dir
        self.GROUPING = fits.open(os.path.join(mbfits_dir, 'GROUPING.fits'))
        self.files = self.GROUPING[1].data['MEMBER_LOCATION']
        self.extnames = self.GROUPING[1].data['EXTNAME']
        self.febes = self.GROUPING[1].data['FEBE']
        self.subsnums = self.GROUPING[1].data['SUBSNUM']
        self.basebands = self.GROUPING[1].data['BASEBAND']

        scan_file = self.files[self.extnames == 'SCAN-MBFITS'][0]
        self.SCAN = fits.open(os.path.join(mbfits_dir, scan_file))

        FEBE_combos = self.SCAN['SCAN-MBFITS'].data['FEBE']
        print(FEBE_combos)
        self.FEBEPARs ={}
        for febe in FEBE_combos:
            self.FEBEPARs[febe] = \
                fits.open(os.path.join(mbfits_dir, febe + '-FEBEPAR.fits'))
        self.time = None

    def read_subscan(self, file):
        hdul = fits.open(os.path.join(self.mbfits_dir, file))
        if self.time is None:
            self.time = hdul[1].data['MJD']
        else:
            try:
                if not np.allclose(self.time, hdul[1].data['MJD']):
                    raise ValueError('MJD mismatch in files')
            except ValueError:
                return None

        return hdul[1].data['DATA']

    def modify_subscan(self):
        pass

    def list_scans(self, febe, baseband):
        good = (self.febes == febe) & (self.basebands == baseband)
        return self.files[good]


class MBFITS_creator():
    def __init__(self, dirname, test=False):
        self.dirname = dirname
        self.test = test
        mkdir_p(dirname)
        curdir = os.path.dirname(__file__)
        datadir = os.path.join(curdir, '..', 'data')
        self.template_dir = os.path.join(datadir, 'mbfits_template')

        self.FEBE = {}

        self.GROUPING = 'GROUPING.fits'
        grouping_template = \
            fits.open(os.path.join(self.template_dir, 'GROUPING.fits'))
        grouping_template[1].data = grouping_template[1].data[:1]

        grouping_template.writeto(os.path.join(self.dirname, self.GROUPING),
                                  overwrite=True)
        grouping_template.close()

        self.SCAN = 'SCAN.fits'
        scan_template = \
            fits.open(os.path.join(self.template_dir, 'SCAN.fits'))
        scan_template[1].data['FEBE'][0] = 'EMPTY'

        scan_template.writeto(os.path.join(self.dirname, self.SCAN),
                              overwrite=True)
        scan_template.close()
        self.scan_count = 0

    def fill_in_summary(self, summaryfile):
        hdul = fits.open(summaryfile)
        header = hdul[0].header

        grouphdul = fits.open(os.path.join(self.dirname, self.GROUPING))
        scanhdul = fits.open(os.path.join(self.dirname, self.SCAN))

        groupheader = grouphdul[0].header
        scanheader = scanhdul[0].header
        hdudict = dict(header.items())
        groupdict = dict(groupheader.items())
        scandict = dict(scanheader.items())

        for key in hdudict.keys():
            if key in groupdict:
                groupheader[key] = hdudict[key]
            if key in scandict:
                scanheader[key] = hdudict[key]

        groupheader['RA'] = np.degrees(hdudict['RightAscension'])
        groupheader['DEC'] = np.degrees(hdudict['Declination'])

        hdul.close()
        grouphdul.writeto(os.path.join(self.dirname, self.GROUPING),
                          overwrite=True)
        scanhdul.writeto(os.path.join(self.dirname, self.SCAN),
                          overwrite=True)
        grouphdul.close()
        scanhdul.close()

    def add_subscan(self, scanfile):
        scan = read_data_fitszilla(scanfile)
        self.scan_count += 1

        chans = get_chan_columns(scan)
        for ch in chans:
            feed = get_channel_feed(ch)
            polar = scan[ch].meta['polarization']
            felabel = scan.meta['receiver'] + '{}{}'.format(feed, polar)
            febe = felabel + '-' + scan.meta['backend']

            subs_par_template = \
                fits.open(os.path.join(self.template_dir, '1',
                                       'FLASH460L-XFFTS-DATAPAR.fits'))
            subs_template = \
                fits.open(os.path.join(self.template_dir, '1',
                                       'FLASH460L-XFFTS-ARRAYDATA-1.fits'))

            n = len(scan)

            ############ Update DATAPAR ############
            subs_par_template[1] = \
                _copy_hdu_and_adapt_length(subs_par_template[1], n)

            newtable = Table(subs_par_template[1].data)
            time = Time(scan['time'] * u.day, scale='utc', format='mjd')
            newtable['MJD'] = scan['time']
            newtable['LST'][:] = \
                time.sidereal_time('apparent',
                                   locations[scan.meta['site']].lon).value
            newtable['INTEGTIM'][:] = scan['Feed0_LCP'].meta['sample_rate']
            newtable['RA'] = scan['ra']
            newtable['DEC'] = scan['dec']
            newtable['LONGOFF'] = 0.
            newtable['LATOFF'] = 0.
            newtable['AZIMUTH'] = scan['az']
            newtable['ELEVATIO'] = scan['el']
            _, direction = scantype(scan['ra'], scan['dec'],
                                    el=scan['el'], az=scan['az'])
            if direction.replace('<', '').replace('>', '').lower() in ['ra', 'dec']:
                baslon, baslat = scan['ra'], scan['dec']
            elif direction.replace('<', '').replace('>', '').lower() in ['el', 'az']:
                baslon, baslat = scan['az'], scan['el']
            else:
                raise ValueError('Unknown coordinates')

            newtable['CBASLONG'] = baslon
            newtable['CBASLAT'] = baslat
            newtable['BASLONG'] = baslon
            newtable['BASLAT'] = baslat

            newhdu = fits.table_to_hdu(newtable)
            subs_par_template[1].data = newhdu.data

            outdir = str(scan.meta['SubScanID'])
            mkdir_p(os.path.join(self.dirname, outdir))
            new_datapar = os.path.join(outdir,
                                       febe + '-DATAPAR.fits')
            subs_par_template.writeto(os.path.join(self.dirname, new_datapar),
                                      overwrite=True)
            subs_par_template.close()

            ############ Update ARRAYDATA ############
            subs_template[1] = \
                _copy_hdu_and_adapt_length(subs_template[1], n)

            subs_template[1].header['SUBSNUM'] = scan.meta['SubScanID']
            subs_template[1].header['DATE-OBS'] = scan.meta['DATE-OBS']
            subs_template[1].header['FEBE'] = scan.meta[febe]
            subs_template[1].header['BASEBAND'] = 1
            subs_template[1].header['CHANNELS'] = scan.meta['channels']

            newtable = Table(subs_template[1].data)
            newtable['MJD'] = scan['time']
            newtable['DATA'] = scan['Feed0_LCP']
            newhdu = fits.table_to_hdu(newtable)
            subs_template[1].data = newhdu.data

            new_sub = \
                os.path.join(outdir, febe + '-ARRAYDATA-1.fits')
            subs_template.writeto(os.path.join(self.dirname, new_sub),
                                  overwrite=True)
            subs_template.close()

            # Finally, update GROUPING file
            grouping = fits.open(os.path.join(self.dirname, self.GROUPING))

            newtable = Table(grouping[1].data)
            if febe not in self.FEBE:
                new_febe = self.add_febe(scan, ch, febe)

                newtable.add_row([2, new_febe, 'URL', 'FEBEPAR-MBFITS',
                                  -999, febe, -999])
            newtable.add_row([2, new_datapar, 'URL', 'DATAPAR-MBFITS',
                              -999, febe, -999])
            newtable.add_row([2, new_sub, 'URL', 'ARRAYDATA-MBFITS',
                              self.scan_count, febe, 1])
            new_hdu = fits.table_to_hdu(newtable)
            grouping[1].data = new_hdu.data
            grouping.writeto(os.path.join(self.dirname, self.GROUPING),
                             overwrite=True)
            if self.test:
                break

    def add_febe(self, scan, channel, febe):
        feed = get_channel_feed(channel)
        meta = scan[channel].meta
        polar = meta['polarization']
        polar_code = polar[0]
        if polar_code == 'H':
            polar_code = 'X'
        elif polar_code == 'V':
            polar_code = 'Y'

        febe_name = febe + '-FEBEPAR.fits'

        febe_template = \
            fits.open(os.path.join(self.template_dir,
                                   'FLASH460L-XFFTS-FEBEPAR.fits'))

        febedata = Table(febe_template[1].data)
        febedata['USEBAND'] = [[1]]
        febedata['USEFEED'] = [[feed]]
        febedata['BESECTS'] = [[0]]
        febedata['FEEDTYPE'] = [[1]]
        febedata['POLTY'][:] = [polar_code + polar_code]
        febedata['POLA'][:] = [[0., 0.]]
        new_hdu = fits.table_to_hdu(febedata)
        febe_template.data = new_hdu.data
        # TODO: fill in the information given in the scan[ch]

        new_febe = os.path.join(self.dirname, febe_name)
        febe_template.writeto(new_febe,
                              overwrite=True)
        febe_template.close()

        scan = fits.open(os.path.join(self.dirname, self.SCAN))
        newtable = Table(scan[1].data)

        if newtable['FEBE'][0].strip() == 'EMPTY':
            newtable['FEBE'][0] = febe
        else:
            newtable.add_row([febe])

        new_hdu = fits.table_to_hdu(newtable)
        scan[1].data = new_hdu.data
        scan.writeto(os.path.join(self.dirname, self.SCAN),
                     overwrite=True)
        return new_febe


if __name__ == '__main__':
    import sys
    from srttools.scan import Scan
    file = MBFits_template(sys.argv[1])
    febe = 'FLASH460L-XFFTS'
    print(file.list_scans(febe, 1))
    print(file.list_scans(febe, 2))
    files = file.list_scans(febe, 1)

    print(file.read_subscan(files[0]))

    created_file = MBFITS_creator('try')

    created_file.add_subscan(sys.argv[2])

    file = MBFits_template('try')

    febe = 'CCB0RCP-ROACH2'
    print(file.list_scans(febe, 1))
    print(file.list_scans(febe, 2))
    files = file.list_scans(febe, 1)

    print(file.read_subscan(files[0]))
