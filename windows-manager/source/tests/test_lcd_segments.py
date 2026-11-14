"""LCD segments have bevelled ends and remain separated on the native grid."""
import unittest
from bitmap_fonts import lcd_cell,native_font
from product_build import compressed_font

def components(mask):
    ink={(x,y) for y in range(mask.height) for x in range(mask.width) if mask.getpixel((x,y))};groups=[]
    while ink:
        todo=[ink.pop()];group=set(todo)
        while todo:
            x,y=todo.pop()
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    p=x+dx,y+dy
                    if p in ink:ink.remove(p);group.add(p);todo.append(p)
        groups.append(group)
    return groups

class LcdSegments(unittest.TestCase):
    def test_all_digits_use_separate_standard_seven_segments_without_corner_contacts(self):
        for ch,count in zip('0123456789',(6,2,5,5,4,5,6,3,7,6)):
            cell=lcd_cell(ch);self.assertEqual(cell.mode,'1');self.assertEqual(cell.size,(50,66))
            groups=components(cell);self.assertEqual(len(groups),count,ch)
            self.assertTrue(all(len(g)>=75 for g in groups),ch)
        self.assertLessEqual(len(compressed_font(native_font('0123456789:',66),5)),1248,'Stay inside the existing clock font slot')

    def test_bevels_keep_a_short_flat_tip_and_the_original_six_pixel_stems(self):
        cell=lcd_cell('8')
        rows=lambda y:sum(bool(cell.getpixel((x,y))) for x in range(7,43))
        self.assertLess(rows(3),rows(5),'Horizontal caps need slanted shoulders')
        self.assertTrue(cell.getpixel((8,5)));self.assertTrue(cell.getpixel((8,6)))
        self.assertFalse(cell.getpixel((8,4)));self.assertFalse(cell.getpixel((8,7)))
        self.assertEqual(sum(bool(cell.getpixel((x,18))) for x in range(5,11)),6)
        self.assertEqual(sum(bool(cell.getpixel((x,32))) for x in range(38,45)),4)
        self.assertEqual(len(components(lcd_cell(':'))),2)

if __name__=='__main__':unittest.main()
