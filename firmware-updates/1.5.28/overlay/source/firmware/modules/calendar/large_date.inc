/* Glyphs stay in the verified OTA bank. Only a single compressed glyph is read at a time. */
#define DATE_CODE __attribute__((section(".large_date"),noinline))
#define DATE_READ ((unsigned (*)(u32,unsigned,void *))0x07fc6829)

DATE_CODE void product_boot_pixels(void){
    const u8 *columns=(const u8 *)0x07fd19a0,*runs=columns+256;
    for(unsigned plane=0;plane<2;plane++){
        u8 *dest=plane?RR:BW;
        for(unsigned x=0;x<250;){
            unsigned count=*runs++,index=*runs++;
            for(x+=count;count;count--)
                for(unsigned j=0;j<16;j++)*dest++=columns[index*16+j];
        }
    }
}

static DATE_CODE u32 date_bank(void){
    CALL0(0x07fc42e8);
    for(u32 bank=0x2000;bank<=0x14000;bank+=0x12000){
        u32 header[2],id;
        if(DATE_READ(bank,8,header)==8 && (header[0]&0xffffff)==0xaa5170 &&
           header[1]==DATE_ATLAS_OFFSET+DATE_ATLAS_SIZE &&
           DATE_READ(bank+64+0xe2f0,4,&id)==4 && id==*(volatile u32 *)(S+28))
            return bank+64+DATE_ATLAS_OFFSET;
    }
    return 0;
}

static DATE_CODE void date_rect(int x,int y,int w,int h,int red){
    for(int j=y;j<y+h;j++)line(x,j,w,red);
}

static DATE_CODE int date_glyph(u32 atlas,const u8 *stamp){
    u8 entry[3],data[255],edges[4]={0};
    unsigned index=stamp[0]-1;
    if(index>=DATE_GLYPH_COUNT || DATE_READ(atlas+3*43*9+3*index,3,entry)!=3)return 0;
    unsigned offset=entry[0]+256*entry[1],length=entry[2],n=0,y=stamp[2];
    if(y>=122||!length||offset+length>DATE_ATLAS_SIZE||DATE_READ(atlas+offset,length,data)!=length)return 0;
    for(unsigned i=0;i<length;){
        unsigned code=data[i++],rows=1;
        if(code==202||code==204){
            n=code-200;if(i+n>length)return 0;
            for(unsigned k=0;k<n;k++)edges[k]=data[i++];
        }else if(code<=80){
            for(unsigned k=0;k<n;k++){
                unsigned q=DIV(code,3);edges[k]+=code-3*q-1;code=q;
            }
        }else rows=code-80;
        if(!n||rows>122-y)return 0;
        for(unsigned j=0;j<n;j+=2){
            unsigned end=stamp[1]+edges[j+1];
            if(edges[j]>=edges[j+1]||end>250)return 0;
            for(unsigned x=stamp[1]+edges[j];x<end;x++){
                unsigned col=(249-x)*16;
                for(unsigned h=y;h<y+rows;h++){
                    unsigned pos=col+(h>>3),bit=128>>(h&7);
                    if(RR[pos]&bit){RR[pos]&=~bit;BW[pos]|=bit;}else BW[pos]&=~bit;
                }
            }
        }
        y+=rows;
    }
    return 1;
}

static DATE_CODE int large_date(unsigned style){
    u32 atlas=date_bank();if(!atlas)return 0;
    if(style<2)date_rect(0,0,style?125:78,122,1);
    else for(unsigned x=5;x<250;x+=125){
        date_rect(x,6,115,27,1);date_rect(x,33,2,83,0);
        date_rect(x+113,33,2,83,0);date_rect(x,114,115,2,0);
    }
    for(unsigned side=0;side<2;side++){
        unsigned record=style*43+(side?12+E[8]:E[7]);u8 stamps[9];
        if(DATE_READ(atlas+record*9,9,stamps)!=9)return 0;
        for(unsigned i=0;i<9&&stamps[i];i+=3)if(!date_glyph(atlas,stamps+i))return 0;
    }
    return 1;
}
