#include "product_runtime.h"
static void font(u32 address){G[14]=address;}
static void pixel(int x,int y,int red){
    if((unsigned)x>=250 || (unsigned)y>=122)return;
    unsigned pos=(249-x)*16+(y>>3),mask=128>>(y&7);
    BW[pos]&=~mask;
    if(red)RR[pos]|=mask;
}
static void line(int x,int y,int w,int red){while(w-->0)pixel(x++,y,red);}
static void text(int x,int y,const char *s,int bold){TEXT(x,y,s);}
static unsigned next_code(const char **ps){
    const u8 *s=(const u8 *)*ps;unsigned c=*s++;
    if(c>=0xe0){c=((c&15)<<12)|((s[0]&63)<<6)|(s[1]&63);s+=2;}
    else if(c>=0xc0){c=((c&31)<<6)|(s[0]&63);s++;}
    *ps=(const char *)s;return c;
}
__attribute__((section(".album.extra"),noinline)) static void compressed_ink(u32 table,int x,int y,const char *s,int red);
static const u8 *glyph(u32 table,unsigned code){
    const u8 *b=(const u8 *)table;unsigned n=*(const u16 *)b;
    for(unsigned i=0;i<n;i++){const u16 *e=(const u16 *)(b+2+i*4);if(e[0]==code)return b+e[1];}
    return 0;
}
__attribute__((section(".album.extra"),noinline)) static void compressed_ink(u32 table,int x,int y,const char *s,int red){
    unsigned n=table==DIGITS?5:4,mask=(1u<<n)-1;
    while(*s){
        const u8 *p=glyph(table,next_code(&s));if(!p)continue;
        const u8 *bits=p+5;unsigned at=0,bit=0;
        while(at<p[1]*p[2]){
            unsigned run=(bits[bit>>3]|(bits[(bit>>3)+1]<<8))>>(bit&7);bit+=2*n;
            at+=run&mask;
            for(unsigned len=(run>>n)&mask;len;len--,at++){
                unsigned row=DIV(at,p[1]);pixel(x+(signed char)p[3]+at-row*p[1],y+(signed char)p[4]+row,red);
            }
        }
        x+=p[0];
    }
}
__attribute__((noinline)) static int width(u32 table,const char *s){
    int w=0;while(*s){const u8 *g=glyph(table,next_code(&s));if(g)w+=g[0];}return w;
}
/* Same glyph placement as the native renderer, but ink may be red. */
__attribute__((noinline)) void product_ink(u32 table,int x,int y,const char *s,int red){
    while(*s){
        const u8 *p=glyph(table,next_code(&s));if(!p)continue;
        unsigned stride=(p[1]+7)>>3;
        for(unsigned j=0;j<p[2];j++)for(unsigned i=0;i<p[1];i++)
            if(p[5+j*stride+(i>>3)]&(128>>(i&7)))pixel(x+(signed char)p[3]+i,y+(signed char)p[4]+j,red);
        x+=p[0];
    }
}
u32 product_battery_percent(void){
    u32 a=*(volatile u16 *)(0x07fd04dc+0x18);
    if(!a)return 255;
    if(a>1705)return 100;
    if(a>1584)return 28+DIV((a-1584)*72,121);
    if(a>1360)return 4+DIV((a-1360)*24,224);
    if(a>1136)return DIV((a-1136)*4,224);
    return 0;
}
__attribute__((noinline)) void product_battery(int x,int y,int label){
    u32 p=product_battery_percent();char t[8];
    /* Bluetooth mark identifies radio capability, not an active connection. */
    static const u16 bt[15]={48,56,60,567,1843,1023,252,120,252,1023,1843,567,60,56,48};
    for(int j=0;j<15;j++)for(int i=0;i<11;i++)if(bt[j]&(1024>>i))pixel(x-18+i,y-2+j,0);
    for(int j=0;j<11;j++)for(int i=0;i<17;i++)if(j<2||j>8||i<2||i>14)pixel(x+i,y+j,0);
    for(int j=3;j<8;j++)for(int i=17;i<19;i++)pixel(x+i,y+j,0);
    if(p!=255)for(unsigned i=0;i<DIV(p*11+50,100);i++)for(int j=3;j<8;j++)pixel(x+3+i,y+j,0);
    if(label){font(SMALL);if(p==255)text(x+24,y-2,"--%",0);
        else {FORMAT(t,"%u%%",p);text(x+24,y-2,t,0);}}
}
/* Boot text is drawn from the font tables: the RLE background has no room for it. */
void product_boot_battery(void){
    product_album_init();
    font(MAIN);text(19,61,"BWR 2.13 / 250x122",0);product_ink(SMALL,148,39,BOOT_VERSION,1);product_battery(194,89,1);
}
static unsigned month_days(unsigned y,unsigned m){
    static const u8 days[12]={31,28,31,30,31,30,31,31,30,31,30,31};
    return days[m]+(m==1 && !(y&3)); /* Supported years 2020..2051, no century exception. */
}
/* Reuse the pinned native solar-term table and names; offsets are zero-based civil days. */
__attribute__((section(".clock.extra"),noinline)) static void next_term(char *t){
    unsigned y=G[2],day=E[8];
    for(unsigned m=0;m<E[7];m++)day+=month_days(y,m);
    for(unsigned add=0;add<2;add++){
        unsigned year=y+add,yy=year-2020,leap=yy?DIV(yy-1,4)+1:0;
        unsigned base=451804+20950*yy-leap*86400;
        const u32 *seconds=(const u32 *)0x07fc7d6c;
        const char *const *names=(const char *const *)0x07fc7dcc;
        for(unsigned i=0;i<24;i++){
            unsigned target=DIV(base+seconds[i],86400)+(add?(365+!(y&3)):0);
            if(target>=day){
                if(target==day)FORMAT(t,"%s今日",names[i]);
                else FORMAT(t,"%s%u天后",names[i],target-day);
                return;
            }
        }
    }
    t[0]=0;
}
int product_sync_valid(const u8 *p){
    unsigned y=p[1]|(p[2]<<8),m=p[3];
    return y>=2020&&y<=2051&&m<12&&p[4]>=1&&p[4]<=month_days(y,m)&&
        p[5]<24&&p[6]<60&&p[7]<60&&p[8]<7&&p[9]<32&&(p[10]&127)<12&&p[11]>=1&&p[11]<=30;
}
static u32 date_key(void){return G[2]*512+E[7]*32+E[8];}
static int time_valid(void){return (S[27]&1)&&G[2]>=2020&&G[2]<=2051&&E[7]<12&&E[8]<month_days(G[2],E[7])&&E[9]<24&&E[10]<60&&G[3]<7;}
int product_timezone(const u8 *packet,unsigned length){
    if(length!=3)return 1;
    unsigned zone=packet[7],summer=packet[8];
    if(zone>1||summer>1||(!zone&&summer))return 1;
    if(S[8]||S[7]==1)return 2;
    S[27]=(S[27]&1)|(zone<<1)|(summer<<2);return 0;
}
__attribute__((section(".clock.extra"),noinline)) int product_control(const u8 *packet,unsigned length){return packet[6]==0x9f?product_timezone(packet,length):packet[6]==0xbd?product_album_cmd(packet,length):product_reminder_cmd(packet,length);}
/* EU/NL rule: last Sunday March 02->03, October 03->02. Native clock counters
   are retained wall time; bit 2 disambiguates October's repeated local hour. */
static void dutch_dst(void){
    if(!(S[27]&2)||G[3]!=0||E[8]<24)return;
    if(E[7]==2&&E[9]>=2&&!(S[27]&4)){E[9]++;S[27]|=4;U->valid=0;}
    if(E[7]==9&&E[9]>=3&&(S[27]&4)){E[9]--;S[27]&=~4;U->valid=0;}
}
static const char *months[12]={"正","二","三","四","五","六","七","八","九","十","冬","腊"};
static void lunar(char *t){
    static const char *digits[10]={"一","二","三","四","五","六","七","八","九","十"};
    unsigned day=G[6]+1,q=DIV(day,10),r=day-q*10;char name[10];
    if(!r)FORMAT(name,"%s十",q==1?"初":q==2?"二":"三");
    else FORMAT(name,"%s%s",q==0?"初":q==1?"十":"廿",digits[r-1]);
    FORMAT(t,"%s%s月%s",G[5]&128?"闰":"",months[G[5]&127],name);
}
#include "modules/calendar/render.inc"
#include "modules/clock/render.inc"
/* Only these native bytes can change during a minute-only update:
   logical x138..240, y24..95; native gates9..111, source bytes3..11. */
static u32 frame_hash(int red){
    u32 h=2166136261u;const u8 *p=red?RR:BW;
    for(unsigned i=0;i<4000;i++){
        unsigned gate=i>>4,src=i&15;
        if(!red&&gate>=9&&gate<=111&&src>=3&&src<=11)continue;
        h=(h^p[i])*16777619u;
    }return h;
}
/* Called by the shared epd_update hook, after complete controller-RAM reload. */
unsigned product_refresh(void){
    unsigned partial=(U->pending && S[7]==0)?U->partial:0;
    /* A full target alone did not remove the user's long-running clock ghosts.
       Erase controller RAM first, retain the target planes, wait asynchronously. */
    unsigned clean=!partial&&(U->count||U->valid==3||(!U->pending&&U->valid&&U->view==0));
    if(!U->pending){U->valid=0;U->partial=0;U->count=0;S[20]=0;}
    if(clean){
        U->valid=2;
        for(int plane=0;plane<2;plane++){
            u8 row[16];for(int j=0;j<16;j++)row[j]=plane?0:255;
            CMD1(0x4e,0);CMD2(0x4f,0,0);CMD(plane?0x26:0x24);
            for(int gate=0;gate<250;gate++)DATA(row,16);
        }
    }
    S[8]=1;S[26]=0;S[9]=0;
    for(unsigned i=0;i<14;i++)((u8 *)0x07fcdc26)[i]=partial==2?0:((const u8 *)0x07fcdc18)[i];
    /* Native minute FLY pulses, with red pixels left undriven (R=1 rows). */
    for(unsigned i=0;i<14;i++)((u8 *)0x07fcdc76)[i]=partial==1?0:((const u8 *)0x07fcdc68)[i];
    if(partial==2){
        /* LUT2/3 are neutral. R=1 masks every pixel outside the minute rectangle.
           This mask is written to controller RAM only; the retained red plane stays exact. */
        CMD1(0x4e,0);CMD2(0x4f,0,0);CMD(0x26);
        static const u8 outside[16]={255,255,255,255,255,255,255,255,255,255,255,255,255,255,255,255};
        static const u8 inside[16]={255,255,255,0,0,0,0,0,0,0,0,0,255,255,255,255};
        for(unsigned gate=0;gate<250;gate++)DATA(gate>=9&&gate<=111?inside:outside,16);
        CMD2(0x0f,9,0);CMD3(0x01,102,0,0);CMD1(0x3c,0);
    }
    return partial==1?2:partial!=0;
}
/* Called after each BUSY poll, including timeout. Commit no reference on failure. */
unsigned product_finish(unsigned busy){
    if(S[9]==4){product_reminder_finish();product_album_finish();U->valid=0;U->pending=0;U->count=0;S[20]=0;return busy;}
    if(busy)return busy;
    if(U->valid==2){
        U->valid=0;U->count=0;S[20]=0;
        CALL0(0x07fc3f68);CALL0(0x07fc40e8);CALL0(0x07fc4174);
        return 1; /* Keep polling, sleep disabled and generation uncommitted. */
    }
    product_reminder_finish();product_album_finish();if(!U->pending)return 0;
    U->outside=U->pending_outside;U->red=U->pending_red;
    U->date=U->pending_date;U->hour=U->pending_hour;U->valid=1;
    if(U->partial)U->count++;else U->count=0;
    S[20]=U->count;
    U->pending=0;U->partial=0;
    return 0;
}
#include "modules/clock/schedule.inc"
#include "modules/calendar/photo.inc"

__attribute__((section(".clock.extra"),noinline)) void product_album_draw(unsigned mode,unsigned crop){
    if(mode){
        if(crop>76)crop=76;
        for(int i=2783;i>=0;i--){BW[1216+i]=BW[(76-crop)*16+i];RR[1216+i]=RR[(76-crop)*16+i];}
        for(unsigned i=0;i<1216;i++){BW[i]=255;RR[i]=0;}
        if(time_valid())photo_calendar();
    }
    U->pending=mode&&time_valid();U->pending_date=date_key();U->view=8;U->partial=0;U->valid=3;product_frame_refresh();
}
