/* Seven-image transactional albums; legacy four-image banks keep their addresses. */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
#define S ((volatile u8 *)0x07fd1980)
#define E ((volatile u32 *)0x07fd04dc)
#define BW ((u8 *)0x07fcdedc)
#define RR ((u8 *)0x07fcf15c)
#define CALL0(a) ((void (*)(void))((a)|1))()
#define READ(a,n,p) ((unsigned (*)(u32,unsigned,void *))0x07fc6829)(a,n,p)
#define ERASE(a,n) ((void (*)(u32,unsigned))0x07fc671d)(a,n)
#define CODE __attribute__((section(".album"),noinline))
#define MAGIC 0x32474c45u
#define RAM_MAGIC 0x414c4231u
struct Config {u32 magic,sequence,crc;u16 minutes;u8 count,flags;u32 frame[7];u8 crop[7],ready;};
struct Album {struct Config current,next;u32 magic,crc;u16 elapsed;u8 loaded,page,running,index,pending,writing,age,resume,step;};
#define A ((volatile struct Album *)0x07fd2140)
typedef char album_config_wire_size[sizeof(struct Config)==52?1:-1];
typedef char album_state_in_existing_tail[sizeof(struct Album)<=128?1:-1];
extern u32 product_crc(u32,const u8 *,unsigned);
extern void product_flash_write(u32,const u8 *,unsigned);
extern void product_publish(const u8 *,unsigned);
extern int product_reminder_blocked(void);
extern void product_album_draw(unsigned,unsigned);
int product_album_tick(void);
CODE static void album_copy(volatile void *dst,const volatile void *src,unsigned n){for(unsigned i=0;i<n;i++)((volatile u8 *)dst)[i]=((const volatile u8 *)src)[i];}
CODE static u32 album_checksum(const struct Config *c,unsigned size){return product_crc(product_crc(~0u,(const u8 *)c,8),(const u8 *)c+12,size)^~0u;}
CODE static int album_valid(const struct Config *c){
    if(c->magic!=MAGIC||c->ready!=254||c->count>7||((c->flags&4)&&!c->count)||c->flags>7||c->minutes<60||c->minutes>10080)return 0;
    for(unsigned i=0;i<7;i++)if(c->crop[i]>84)return 0;
    return c->crc==album_checksum(c,39);
}
__attribute__((section(".album.extra"),noinline)) static int album_legacy(struct Config *c){
    u8 *p=(u8 *)c;
    if(c->magic!=0x31474c45u||p[38]!=254||c->count>4||p[15]>1||p[36]>1||p[37]>1||(p[37]&&!c->count))return 0;
    if(c->crc!=album_checksum(c,26))return 0;
    for(unsigned i=0;i<4;i++)if(p[32+i]>84)return 0;
    c->flags=p[15]|(p[36]<<1)|(p[37]<<2);
    for(unsigned i=0;i<4;i++)c->crop[i]=p[32+i];
    for(unsigned i=4;i<7;i++){c->frame[i]=0;c->crop[i]=0;}
    c->magic=MAGIC;c->ready=254;c->crc=album_checksum(c,39);return 1;
}
__attribute__((section(".clock.extra"),noinline)) static int album_empty(u32 start,u32 end){u8 b[64];for(;start<end;start+=64){if(READ(start,64,b)!=64)return 0;for(unsigned i=0;i<64;i++)if(b[i]!=255)return 0;}return 1;}
__attribute__((section(".clock.extra"),noinline)) static u32 album_address(unsigned bank,unsigned slot){return slot<4?0x42000+(bank<<15)+(slot<<13):0x52000+bank*0x6000+((slot-4)<<13);}
CODE static int album_load(void){
    if(A->loaded)return A->loaded==1;
    CALL0(0x07fc42e8);
    if(((unsigned (*)(void))0x07fc6891)()!=0xa112){A->loaded=2;return 0;}
    struct Config c[2];if(READ(0x40000,52,c)!=52||READ(0x41000,52,c+1)!=52)return 0;
    int old0=album_legacy(c),old1=album_legacy(c+1);
    int a=album_valid(c),b=album_valid(c+1);A->page=255;
    if(a||b){A->page=b&&(!a||(int)(c[1].sequence-c[0].sequence)>0);if((A->page?old1:old0)&&!album_empty(0x52000,0x5e000))return 0;album_copy(&A->current,c+A->page,52);}
    A->loaded=1;A->running=A->resume&&A->page!=255&&(A->current.flags&4);A->index=255;A->elapsed=0;
    return 1;
}
CODE void product_album_init(void){
    for(unsigned i=0;i<sizeof(struct Album);i++)((volatile u8 *)A)[i]=0;
    A->magic=RAM_MAGIC;A->resume=*(volatile u16 *)(S+18)==0;
}
CODE static int album_save(void){
    struct Config c;album_copy(&c,&A->next,52);c.magic=MAGIC;c.sequence=A->page==255?1:A->current.sequence+1;c.ready=255;c.crc=album_checksum(&c,39);
    unsigned page=A->page==255?0:A->page^1;u32 addr=0x40000+(page<<12);
    ERASE(addr,4096);product_flash_write(addr,(const u8 *)&c,52);
    struct Config check;if(READ(addr,52,&check)!=52||check.crc!=c.crc||check.sequence!=c.sequence)return 0;check.ready=254;if(!album_valid(&check))return 0;
    u8 ready=254;product_flash_write(addr+51,&ready,1);if(READ(addr,52,&check)!=52)return 0;if(!album_valid(&check))return 0;
    album_copy(&A->current,&check,52);A->page=page;return 1;
}
__attribute__((section(".album.extra"),noinline)) static int album_initialize(void){
    if(A->page!=255)return 1;
    if(A->crc!=120)return 0;A->crc=0;
    for(unsigned i=0;i<52;i++)((volatile u8 *)&A->next)[i]=0;
    A->next.minutes=1440;return album_save();
}
CODE int product_album_cmd(const u8 *message,unsigned n){
    const u8 *p=message+6;
    if(n<2||p[0]!=0xbd||p[1]>6)return 1;
    if(S[8]||*(volatile u32 *)0x07fd0564||(p[1]>0&&p[1]<4&&product_reminder_blocked()))return 2;
    if(A->magic!=RAM_MAGIC)product_album_init();
    if(!album_load())return 6;CALL0(0x07fc42e8);
    if(p[1]==0){
        if(n!=2)return 1;u8 b[64]={'E','L','A','1',3};b[5]=A->page!=255;b[6]=!!A->running;b[7]=A->index;
        b[8]=A->writing;b[9]=A->next.count;unsigned progress=A->writing?A->step:A->elapsed;b[10]=progress;b[11]=progress>>8;album_copy(b+12,&A->current,52);product_publish(b,64);return 0;
    }
    if(p[1]==6){
        // A->crc is a read-only preflight cursor until staging starts; every dedicated byte must be checked.
        if(n!=3||A->page!=255||A->writing||p[2]>=120)return 1;
        unsigned part=p[2];if(!part)A->crc=0;
        if(A->crc==part){if(!album_empty(0x40000+(part<<10),0x40400+(part<<10))){A->crc=0;return 6;}A->crc++;}
        else if(A->crc!=part+1)return 1;
        u8 b[8]={'E','L','A','P',A->crc,120};product_publish(b,8);return 0;
    }
    if(p[1]==5){if(n!=5||A->page==255||A->writing||p[2]>=A->current.count)return 1;unsigned off=p[3]|(p[4]<<8);if(off>=8000)return 1;unsigned size=8000-off;if(size>128)size=128;u8 b[128];if(READ(album_address((A->current.flags>>1)&1,p[2])+off,size,b)!=size)return 5;product_publish(b,size);return 0;}
    if(p[1]==1){
        if(n!=2)return 1;if(!album_initialize())return 6;
        album_copy(&A->next,&A->current,52);A->next.flags^=2;A->next.count=0;A->writing=1;A->step=0;A->age=0;S[7]=2;return 0;
    }
    if(p[1]==2){
        if(n!=9||!A->writing||p[2]!=A->next.count||p[2]>=7||p[3]>84||p[8]!=A->step||p[8]>=32||S[7]!=1||*(volatile u16 *)(S+10)!=8000||*(volatile u16 *)(S+14)!=*(volatile u16 *)(S+16))return 1;
        u32 expected=p[4]|(p[5]<<8)|(p[6]<<16)|((u32)p[7]<<24);
        u32 addr=album_address((A->next.flags>>1)&1,p[2]);unsigned step=A->step;
        if(!step){if((product_crc(product_crc(~0u,BW,4000),RR,4000)^~0u)!=expected)return 1;A->crc=~0u;ERASE(addr,4096);}
        if(step==16)ERASE(addr+4096,4096);
        // 250 divides both 4000-byte planes; each request yields after at most two page programs.
        addr+=step*250;product_flash_write(addr,(step<16?BW:RR)+(step%16)*250,250);
        u8 b[50];for(unsigned i=0;i<250;i+=50){if(READ(addr+i,50,b)!=50)return 5;A->crc=product_crc(A->crc,b,50);}
        A->age=0;if(++A->step!=32)return 0;
        if((A->crc^~0u)!=expected)return 5;
        A->next.frame[p[2]]=expected;A->next.crop[p[2]]=p[3];A->next.count++;A->step=0;S[7]=2;return 0;
    }
    if(p[1]==4){
        if(n!=2)return 1;A->writing=0;A->step=0;A->running=0;if(A->page==255)return 0;
        album_copy(&A->next,&A->current,52);A->next.flags&=~4;return album_save()?0:5;
    }
    if(n!=5||p[2]>1)return 1;
    unsigned minutes=p[3]|(p[4]<<8);if(minutes<60||minutes>10080)return 1;
    if(!A->writing)album_copy(&A->next,&A->current,52);
    if(!A->next.count||(A->writing&&A->step))return 1;
    A->next.flags=(A->next.flags&2)|p[2]|4;A->next.minutes=minutes;
    if(!album_save())return 5;
    A->writing=0;A->running=1;A->index=255;A->elapsed=0;product_album_tick();return S[9]?5:0;
}
CODE int product_album_tick(void){
    if(A->magic!=RAM_MAGIC||A->loaded!=1||!A->running||A->writing||A->pending||S[8]||*(volatile u32 *)0x07fd0564||product_reminder_blocked())return 0;
    if(A->index!=255&&S[7]!=7&&S[7]!=8){A->running=0;return 0;}
    if(A->index!=255&&(A->current.count==1||A->elapsed<A->current.minutes))return 0;
    unsigned next=A->index==255?0:A->index+1;if(next>=A->current.count)next=0;
    CALL0(0x07fc42e8);u32 addr=album_address((A->current.flags>>1)&1,next);
    if(READ(addr,4000,BW)!=4000||READ(addr+4000,4000,RR)!=4000||(product_crc(product_crc(~0u,BW,4000),RR,4000)^~0u)!=A->current.frame[next]){A->running=0;S[7]=2;S[9]=5;return 1;}
    A->pending=next+1;S[7]=7+(A->current.flags&1);product_album_draw(A->current.flags&1,A->current.crop[next]);return 1;
}
CODE void product_album_finish(void){
    if(A->magic!=RAM_MAGIC||!A->pending)return;
    if(S[9])A->running=0;else{A->index=A->pending-1;A->elapsed=0;}
    A->pending=0;
}
CODE int product_album_restore(void){
    if(A->magic!=RAM_MAGIC||!A->running||A->index==255)return 0;
    A->elapsed=A->current.minutes;A->index=A->current.count==1?255:A->index?A->index-1:A->current.count-1;S[7]=7+(A->current.flags&1);return 1;
}
CODE void product_minute_tick(void){
    CALL0(0x07fc31c8);
    if(A->magic!=RAM_MAGIC)return;
    if(!album_load())return;
    if(A->writing){if(++A->age>=5){A->writing=0;A->index=255;}return;}
    if(S[8]||*(volatile u32 *)0x07fd0564||product_reminder_blocked())return;
    if(A->running&&A->elapsed<A->current.minutes)A->elapsed++;
    if(!(S[27]&1))product_album_tick();
}
